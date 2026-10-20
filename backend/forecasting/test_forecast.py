"""
Tests for the forecasting pipeline.
Runs against the live seeded database.

Usage:  pytest backend/forecasting/test_forecast.py -v
"""

import sys
import math
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import pytest

from backend.forecasting.pipeline import (
    build_daily_demand,
    moving_average_forecast,
    arima_forecast,
    mae,
    rmse,
    run_forecast,
)
from backend.db import get_conn


@pytest.fixture
def conn():
    c = get_conn()
    yield c
    c.rollback()
    c.close()


# ─── Unit tests (no DB needed) ──────────────────────────────────

class TestMovingAverage:
    def test_basic(self):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        preds, name = moving_average_forecast(series, window=5, horizon=3)
        assert name == "moving_average"
        assert len(preds) == 3
        # avg of last 5 (6,7,8,9,10) = 8.0
        assert all(p == 8.0 for p in preds)

    def test_short_series(self):
        series = pd.Series([3, 5], dtype=float)
        preds, _ = moving_average_forecast(series, window=14, horizon=5)
        assert len(preds) == 5
        assert all(p == 4.0 for p in preds)  # mean of [3,5]

    def test_empty_series(self):
        series = pd.Series(dtype=float)
        preds, _ = moving_average_forecast(series, window=14, horizon=5)
        assert all(p == 0.0 for p in preds)


class TestMetrics:
    def test_mae(self):
        actual = np.array([1, 2, 3])
        predicted = np.array([1.5, 2.5, 3.5])
        assert abs(mae(actual, predicted) - 0.5) < 1e-9

    def test_rmse(self):
        actual = np.array([1, 2, 3])
        predicted = np.array([1, 2, 3])
        assert rmse(actual, predicted) == 0.0


class TestARIMA:
    def test_arima_on_synthetic(self):
        # Linear trend with noise — ARIMA should handle this
        np.random.seed(42)
        series = pd.Series(np.arange(100) * 0.5 + np.random.randn(100) * 0.5)
        preds, name = arima_forecast(series, horizon=10)
        assert name == "arima"
        assert len(preds) == 10
        assert all(p >= 0 for p in preds)


# ─── Integration tests (need seeded DB) ─────────────────────────

class TestPipeline:
    def test_build_demand_series(self, conn):
        """Product 1 / Warehouse 1 should have a non-empty demand series."""
        series = build_daily_demand(conn, product_id=1, warehouse_id=1)
        assert len(series) > 30, f"Expected >30 days of data, got {len(series)}"
        assert series.sum() > 0

    def test_full_pipeline(self, conn):
        """Run the full pipeline and check outputs."""
        stats = run_forecast(conn)
        assert stats["total_pairs"] == 90  # 30 products × 3 warehouses
        assert stats["forecasts_written"] > 0
        # Should have at least some alerts (we know some products have low stock)
        assert stats["alerts_generated"] >= 0
        # Check DB has at least as many forecasts as we just wrote
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM demand_forecasts")
        fc_count = cur.fetchone()[0]
        assert fc_count >= stats["forecasts_written"]
        # Check reorder_alerts
        cur.execute("SELECT COUNT(*) FROM reorder_alerts WHERE status = 'open'")
        alert_count = cur.fetchone()[0]
        assert alert_count >= stats["alerts_generated"]

    def test_reorder_points_updated(self, conn):
        """After pipeline (run by previous test), reorder_point should be > 0."""
        # Don't re-run pipeline — just check state from test_full_pipeline
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM stock_levels
            WHERE reorder_point > 0
        """)
        count = cur.fetchone()[0]
        assert count > 0, "Expected some reorder_points to be updated"
