# StockSense — AI-Powered Inventory Management System

> **Course Project** — Database Systems  
> Stack: PostgreSQL 16 · Python 3.11+ / FastAPI · Statsmodels / Pandas · React (Vite) · Docker Compose

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       React Frontend                        │
│   Stock Levels · Reorder Alerts · Forecast Charts · Forms   │
└──────────────────────────────┬──────────────────────────────┘
                               │ REST / JSON (port 8000)
┌──────────────────────────────▼──────────────────────────────┐
│                     FastAPI Backend                         │
│   CRUD · /sales (atomic deduct) · /purchase-orders/receive  │
│         /forecasts/run · Pydantic Validation · CORS         │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               │ ML Pipeline                  │ SQL / Transactions
               │ (MA + ARIMA)                 │
┌──────────────▼──────────────┐┌──────────────▼───────────────┐
│     Forecasting Engine      ││        PostgreSQL 16         │
│  Daily aggregation · Train/ ││   12 tables (strict 3NF)     │
│  Holdout MAE · Dynamic ROP  ││   Views · Triggers · Stored  │
│  Reorder Alert Generation   ││   Procedures · 18 Indexes    │
└─────────────────────────────┘└──────────────────────────────┘
```

---

## Entity-Relationship Summary

```
categories 1───∞ products ∞───1 suppliers
                      │
                      │ 1
                      ├──────────∞ stock_levels ∞───1 warehouses
                      │                                    │
                      ├──────────∞ demand_forecasts ∞──────┘
                      │
                      ├──────────∞ reorder_alerts
                      │
                      ├──────────∞ sales_transaction_items ∞───1 sales_transactions
                      │                                              │
                      │                                         customers
                      │
                      └──────────∞ purchase_order_items ∞───1 purchase_orders
                                                                  │
                                                             suppliers
```

### Key Relationships

| Parent | Child | FK Column | ON DELETE | Rationale |
|---|---|---|---|---|
| categories | products | category_id | RESTRICT | Prevent deleting categories in use |
| suppliers | products | supplier_id | RESTRICT | Products must have a valid supplier |
| products | stock_levels | product_id | CASCADE | Deleting product deletes its stock rows |
| warehouses | stock_levels | warehouse_id | CASCADE | Deleting warehouse deletes its stock rows |
| customers | sales_transactions | customer_id | RESTRICT | Preserve historical sales data |
| warehouses | sales_transactions | warehouse_id | RESTRICT | Preserve transaction history |
| sales_transactions | sales_transaction_items | sale_id | CASCADE | Line items belong to the sale header |
| products | sales_transaction_items | product_id | RESTRICT | Cannot delete product with sales history |
| suppliers | purchase_orders | supplier_id | RESTRICT | Preserve PO history |
| purchase_orders | purchase_order_items | po_id | CASCADE | Line items belong to the PO header |
| products | purchase_order_items | product_id | RESTRICT | Cannot delete product with PO history |
| products | demand_forecasts | product_id | CASCADE | Forecasts follow products |
| warehouses | demand_forecasts | warehouse_id | CASCADE | Forecasts follow warehouses |
| demand_forecasts | reorder_alerts | forecast_id | SET NULL | Keep alert history even if forecast re-run |
| products | reorder_alerts | product_id | CASCADE | Alerts follow products |
| warehouses | reorder_alerts | warehouse_id | CASCADE | Alerts follow warehouses |
| suppliers | reorder_alerts | supplier_id | RESTRICT | Preserve supplier reference |

---

## Viva Notes (Key Design Decisions)

### 1. Strict 3NF Choices
* **No computed values stored**: `available_qty` (`quantity_on_hand - reserved_qty`) and `line_total` (`quantity * unit_price - discount`) live in **views** (`v_available_stock`, `v_sales_line_totals`), never stored columns. This eliminates update anomalies.
* **`reorder_point` in `stock_levels`, not `products`**: Different warehouses experience different demand velocities and lead times (e.g. Mumbai vs Delhi depot). Reorder threshold is a property of the *product-at-location*, not the product alone.
* **`lead_time_days` in `products`**: In our single-sourcing model, lead time is functionally dependent on the product-supplier pair. If multi-sourcing were added, it would move to a `product_suppliers` junction table.

### 2. Triggers vs API Transactions
* **Database Trigger (`trg_block_negative_stock`)**: Enforces that `quantity_on_hand` cannot drop below zero at the DB engine level. Even if an engineer runs an ad-hoc SQL query or a bug exists in the application layer, the DB rejects over-deduction.
* **Stored Functions (`fn_deduct_stock`, `fn_receive_stock`)**: Encapsulate atomic stock mutations in a single round-trip. The API wraps header + multiple line items in a database transaction, delegating line-level stock mutations to the stored procedures.
* **Why both?** Defense-in-depth: API provides coarse-grained transaction boundaries (commit all or nothing), DB trigger guarantees physical invariant (no negative stock).

### 3. Forecasting Models
* **Moving Average (14-day)**: Robust baseline for noisy, intermittent retail demand. Low variance, immune to non-stationarity, and handles zero-inflated series gracefully.
* **ARIMA(1,1,1)**: Captures autocorrelation, momentum, and short-term trends.
* **Holdout Evaluation**: For each product-warehouse pair, the last 20% of history is held out. Both models predict the holdout; the model with the lower **MAE (Mean Absolute Error)** is selected for that specific series.
* **Dynamic Reorder Point Formula**:
  $$\text{Reorder Point} = (\text{Daily Demand Forecast} \times \text{Lead Time Days}) + \text{Safety Stock}$$
  $$\text{Safety Stock} = \text{Daily Demand Forecast} \times 3\text{ days}$$
  When available stock $\le$ Reorder Point, an automated reorder alert is generated.

---

## How to Run Everything (Windows / PowerShell)

### Prerequisites
* Docker Desktop running
* Python 3.11+
* Node.js 18+

### Step 1: Start PostgreSQL (Docker)
Open PowerShell in `stock-sense/`:

```powershell
# Start database container
docker compose up -d

# Verify container is healthy
docker compose ps

# Verify schema and seed loaded
docker compose exec db psql -U stocksense -d stocksense -c "\dt"
```

Expected output: 12 tables listed.

### Step 2: Run Trigger Tests (PowerShell-safe)
Because PowerShell does not support `<` input redirection, pass the file inside the container:

```powershell
docker compose exec db psql -U stocksense -d stocksense -f /docker-entrypoint-initdb.d/../db/test_trigger.sql
```
*Or copy and run directly:*
```powershell
Get-Content db\test_trigger.sql | docker compose exec -T db psql -U stocksense -d stocksense
```
Expected output: Two `PASS` lines, zero `FAIL`s.

### Step 3: Run the Forecasting Pipeline
In PowerShell from the `stock-sense/` root:

```powershell
# Install backend dependencies
pip install -r requirements.txt

# Run forecasting pipeline directly
python backend\forecasting\pipeline.py

# Or run tests
pytest backend\forecasting\test_forecast.py -v
```

### Step 4: Start the FastAPI Backend
```powershell
# Set Python path and start uvicorn
$env:PYTHONPATH = "."
uvicorn backend.api:app --reload --port 8000
```
* Interactive API docs: http://localhost:8000/docs
* Run API tests in a separate terminal:
```powershell
pytest backend\test_api.py -v
```

### Step 5: Start the React Frontend
Open a new PowerShell terminal in `stock-sense\frontend`:

```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 in your browser.

---

## Roadmap / Implementation Status

| Phase | Description | Status | Verification |
|---|---|---|---|
| **1** | Schema (3NF), triggers, views, indexes, Docker | ✅ Done | Tested against live Postgres 17; trigger test passes |
| **2** | Synthetic seed data (18 mos, 30 prods, 3 WHs) | ✅ Done | 4,292 lines loaded; 1,252 sales; 34 POs; realistic seasonality |
| **3** | Forecasting pipeline (MA + ARIMA + holdout MAE) | ✅ Done | 9/9 pytest tests PASS; dynamic ROP + reorder alerts generated |
| **4** | FastAPI REST API (CRUD, atomic sales/POs, CORS) | ✅ Done | 20/20 pytest tests PASS; 409 on insufficient stock verified |
| **5** | React dashboard (Stock table, alerts, chart, forms) | ✅ Done | `npm run build` succeeds; Vite production bundle built |
