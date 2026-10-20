"""
StockSense — Demand Forecasting Pipeline

For each product/warehouse pair:
1. Builds a daily demand time-series from sales_transaction_items.
2. Splits into train (first 80%) and holdout (last 20%).
3. Fits a 14-day Moving Average and an ARIMA(1,1,1) model.
4. Picks the model with lower MAE on the holdout set.
5. Writes 30-day-ahead forecasts to demand_forecasts.
6. Computes dynamic reorder_point = (avg_daily_forecast × lead_time) + safety_stock.
7. Updates stock_levels.reorder_point.
8. Generates reorder_alerts where available stock ≤ reorder_point.

Graceful fallbacks:
- Series shorter than 30 days → Moving Average only (ARIMA needs history).
- All-zero series → predicted_demand = 0, reorder_point left at current value.
- ARIMA convergence failure → fall back to Moving Average.
"""

import os
import sys
import warnings
import math
from datetime import date, timedelta
from pathlib import Path

# Ensure project root is in sys.path regardless of execution directory or platform
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings("ignore")  # suppress statsmodels convergence warnings


# ─── Time-series construction ───────────────────────────────────

def build_daily_demand(conn, product_id: int, warehouse_id: int) -> pd.Series:
    """
    Query sales and build a daily demand series (units sold per day).
    Returns a pandas Series indexed by date.
    """
    sql = """
        SELECT st.sale_date, SUM(si.quantity) AS daily_qty
        FROM sales_transaction_items si
        JOIN sales_transactions st ON st.sale_id = si.sale_id
        WHERE si.product_id = %s
          AND st.warehouse_id = %s
          AND st.status = 'completed'
        GROUP BY st.sale_date
        ORDER BY st.sale_date
    """
    df = pd.read_sql(sql, conn, params=(product_id, warehouse_id))
    if df.empty:
        return pd.Series(dtype=float)

    # Fill missing dates with 0 (no sales that day)
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    df = df.set_index("sale_date")
    full_range = pd.date_range(df.index.min(), df.index.max(), freq="D")
    series = df["daily_qty"].reindex(full_range, fill_value=0).astype(float)
    series.index.name = "date"
    return series


# ─── Models ──────────────────────────────────────────────────────

def moving_average_forecast(series: pd.Series, window: int = 14, horizon: int = 30):
    """
    Simple moving average: predicts the next `horizon` days as the
    average of the last `window` days.  Dead simple, but surprisingly
    competitive for noisy low-volume retail data.

    Returns: (predictions array of length horizon, model_name)
    """
    if len(series) < window:
        avg = series.mean() if len(series) > 0 else 0.0
    else:
        avg = series.iloc[-window:].mean()
    avg = max(0.0, avg)
    return np.full(horizon, avg), "moving_average"


def arima_forecast(series: pd.Series, horizon: int = 30):
    """
    ARIMA(1,1,1) forecast.  Returns (predictions, model_name) or
    raises an exception if the model can't converge.
    """
    # ARIMA needs at least ~30 data points to be meaningful
    model = ARIMA(series, order=(1, 1, 1))
    result = model.fit()
    preds = result.forecast(steps=horizon)
    # Clip negatives — demand can't be negative
    preds = np.maximum(preds, 0.0)
    return preds, "arima"


# ─── Evaluation ──────────────────────────────────────────────────

def mae(actual, predicted):
    return np.mean(np.abs(actual - predicted))


def rmse(actual, predicted):
    return np.sqrt(np.mean((actual - predicted) ** 2))


# ─── Main pipeline ──────────────────────────────────────────────

def run_forecast(conn, forecast_horizon: int = 30, ma_window: int = 14,
                 safety_stock_days: int = 3):
    """
    Run the full forecasting pipeline for all product/warehouse pairs.
    Returns a summary dict with counts.
    """
    cur = conn.cursor()

    # Get all product/warehouse pairs that have stock_levels rows
    cur.execute("""
        SELECT sl.product_id, sl.warehouse_id, p.lead_time_days, p.supplier_id,
               sl.quantity_on_hand, sl.reserved_qty
        FROM stock_levels sl
        JOIN products p ON p.product_id = sl.product_id
    """)
    pairs = cur.fetchall()

    stats = {
        "total_pairs": len(pairs),
        "forecasts_written": 0,
        "alerts_generated": 0,
        "models_chosen": {"moving_average": 0, "arima": 0},
        "skipped_zero": 0,
        "arima_fallbacks": 0,
    }

    # Clear old forecasts and open alerts (fresh run)
    cur.execute("DELETE FROM reorder_alerts WHERE status = 'open'")
    cur.execute("DELETE FROM demand_forecasts")

    today = date.today()

    for product_id, warehouse_id, lead_time, supplier_id, qty_on_hand, reserved_qty in pairs:
        series = build_daily_demand(conn, product_id, warehouse_id)

        # Skip if no sales history at all
        if len(series) == 0 or series.sum() == 0:
            stats["skipped_zero"] += 1
            continue

        # Train/holdout split (80/20)
        split_idx = int(len(series) * 0.8)
        train = series.iloc[:split_idx]
        holdout = series.iloc[split_idx:]

        # Moving Average on holdout
        ma_preds_holdout, _ = moving_average_forecast(train, window=ma_window,
                                                       horizon=len(holdout))
        ma_mae = mae(holdout.values, ma_preds_holdout[:len(holdout)])

        # ARIMA on holdout (with fallback)
        arima_mae = float("inf")
        arima_ok = False
        if len(train) >= 30:
            try:
                arima_model = ARIMA(train, order=(1, 1, 1))
                arima_result = arima_model.fit()
                arima_preds_holdout = np.maximum(arima_result.forecast(steps=len(holdout)), 0.0)
                arima_mae = mae(holdout.values, arima_preds_holdout[:len(holdout)])
                arima_ok = True
            except Exception:
                stats["arima_fallbacks"] += 1

        # Pick the better model
        if arima_ok and arima_mae < ma_mae:
            chosen_model = "arima"
            # Re-fit on full data for final forecast
            try:
                final_model = ARIMA(series, order=(1, 1, 1))
                final_result = final_model.fit()
                final_preds = np.maximum(final_result.forecast(steps=forecast_horizon), 0.0)
            except Exception:
                # Fallback if full-data fit fails
                final_preds, _ = moving_average_forecast(series, ma_window, forecast_horizon)
                chosen_model = "moving_average"
                stats["arima_fallbacks"] += 1
        else:
            chosen_model = "moving_average"
            final_preds, _ = moving_average_forecast(series, ma_window, forecast_horizon)

        stats["models_chosen"][chosen_model] += 1

        # Write forecasts to demand_forecasts
        forecast_ids = []
        for i, pred in enumerate(final_preds):
            forecast_date = today + timedelta(days=i + 1)
            cur.execute("""
                INSERT INTO demand_forecasts
                    (product_id, warehouse_id, forecast_date, predicted_demand, model_used)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING forecast_id
            """, (product_id, warehouse_id, forecast_date, round(float(pred), 2), chosen_model))
            forecast_ids.append(cur.fetchone()[0])
            stats["forecasts_written"] += 1

        # Dynamic reorder point:
        #   avg_daily_forecast × lead_time_days + safety_stock
        #   safety_stock = avg_daily_forecast × safety_stock_days
        avg_daily = float(np.mean(final_preds))
        dynamic_reorder_point = max(1, math.ceil(avg_daily * lead_time + avg_daily * safety_stock_days))

        cur.execute("""
            UPDATE stock_levels SET reorder_point = %s, last_updated = now()
            WHERE product_id = %s AND warehouse_id = %s
        """, (dynamic_reorder_point, product_id, warehouse_id))

        # Generate reorder alert if available stock ≤ reorder point
        available = qty_on_hand - reserved_qty
        if available <= dynamic_reorder_point:
            suggested_qty = max(1, math.ceil(avg_daily * (lead_time + safety_stock_days * 2)) - available)
            # Use the first forecast_id as reference
            ref_forecast_id = forecast_ids[0] if forecast_ids else None
            cur.execute("""
                INSERT INTO reorder_alerts
                    (forecast_id, product_id, warehouse_id, supplier_id,
                     alert_date, suggested_order_qty, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'open')
            """, (ref_forecast_id, product_id, warehouse_id, supplier_id,
                  today, suggested_qty))
            stats["alerts_generated"] += 1

    conn.commit()
    return stats


def main():
    """CLI entry point: connect, run, print summary."""
    import json
    import sys
    from pathlib import Path

    # This file lives at <project_root>/backend/forecasting/pipeline.py,
    # so the project root is two folders up. Works on Windows, Linux and Docker.
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    from backend.db import get_conn

    conn = get_conn()
    try:
        stats = run_forecast(conn)
        print(json.dumps(stats, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()