-- StockSense: AI-Powered Inventory Management System
-- Phase 1: Logical Schema (strict 3NF)
-- All tables use SERIAL PKs for simplicity. UUIDs could be used in production.

BEGIN;

-- =============================================================
-- TABLES
-- =============================================================

-- Product categories (top-level grouping)
CREATE TABLE categories (
    category_id   SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,  -- no duplicate category names
    description   TEXT
);

-- Suppliers who fulfill purchase orders
CREATE TABLE suppliers (
    supplier_id    SERIAL PRIMARY KEY,
    supplier_name  VARCHAR(200) NOT NULL,
    contact_person VARCHAR(200),
    email          VARCHAR(254),                 -- RFC 5321 max local+domain
    phone          VARCHAR(20),
    address        TEXT
);

-- Products: the items we track
-- lead_time_days lives here because it's a property of the product-supplier
-- relationship (1 supplier per product in this model).
CREATE TABLE products (
    product_id     SERIAL PRIMARY KEY,
    sku            VARCHAR(50)  NOT NULL UNIQUE,  -- human-readable stock-keeping unit
    product_name   VARCHAR(200) NOT NULL,
    description    TEXT,
    category_id    INT NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
    supplier_id    INT NOT NULL REFERENCES suppliers(supplier_id) ON DELETE RESTRICT,
    unit_price     NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    lead_time_days INT NOT NULL CHECK (lead_time_days >= 0)
);

-- Physical storage locations
CREATE TABLE warehouses (
    warehouse_id   SERIAL PRIMARY KEY,
    warehouse_name VARCHAR(200) NOT NULL UNIQUE,
    location       VARCHAR(200),   -- city / region label
    address        TEXT
);

-- Current stock snapshot per product per warehouse.
-- reorder_point lives here (not in products) because it can differ by warehouse.
CREATE TABLE stock_levels (
    stock_id         SERIAL PRIMARY KEY,
    product_id       INT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    warehouse_id     INT NOT NULL REFERENCES warehouses(warehouse_id) ON DELETE CASCADE,
    quantity_on_hand INT NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
    reserved_qty     INT NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),
    reorder_point    INT NOT NULL DEFAULT 0 CHECK (reorder_point >= 0),
    last_updated     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, warehouse_id)  -- one row per product-warehouse pair
);

-- Customers who buy from us
CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL,
    email         VARCHAR(254),
    phone         VARCHAR(20),
    address       TEXT
);

-- Sales header: one row per transaction
CREATE TABLE sales_transactions (
    sale_id        SERIAL PRIMARY KEY,
    customer_id    INT NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    warehouse_id   INT NOT NULL REFERENCES warehouses(warehouse_id) ON DELETE RESTRICT,
    sale_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    total_amount   NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    payment_method VARCHAR(50) CHECK (payment_method IN ('cash','card','upi','bank_transfer','other')),
    status         VARCHAR(20)  NOT NULL DEFAULT 'completed'
                   CHECK (status IN ('pending','completed','cancelled','refunded'))
);

-- Sales line items (child of sales_transactions)
-- line_total is computed, not stored → avoids update anomalies (3NF).
CREATE TABLE sales_transaction_items (
    sale_item_id SERIAL PRIMARY KEY,
    sale_id      INT NOT NULL REFERENCES sales_transactions(sale_id) ON DELETE CASCADE,
    product_id   INT NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity     INT NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    discount     NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount >= 0)
);

-- Purchase order header
CREATE TABLE purchase_orders (
    po_id         SERIAL PRIMARY KEY,
    supplier_id   INT NOT NULL REFERENCES suppliers(supplier_id) ON DELETE RESTRICT,
    order_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    expected_date DATE,
    status        VARCHAR(20) NOT NULL DEFAULT 'ordered'
                  CHECK (status IN ('ordered','partial','received','cancelled')),
    total_amount  NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0)
);

-- Purchase order line items
CREATE TABLE purchase_order_items (
    po_item_id   SERIAL PRIMARY KEY,
    po_id        INT NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    product_id   INT NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity     INT NOT NULL CHECK (quantity > 0),
    unit_cost    NUMERIC(12,2) NOT NULL CHECK (unit_cost >= 0),
    received_qty INT NOT NULL DEFAULT 0 CHECK (received_qty >= 0)
);

-- ML demand forecasts (written by the forecasting pipeline)
CREATE TABLE demand_forecasts (
    forecast_id      SERIAL PRIMARY KEY,
    product_id       INT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    warehouse_id     INT NOT NULL REFERENCES warehouses(warehouse_id) ON DELETE CASCADE,
    forecast_date    DATE NOT NULL,
    predicted_demand NUMERIC(12,2) NOT NULL CHECK (predicted_demand >= 0),
    model_used       VARCHAR(50) NOT NULL,       -- e.g. 'moving_average', 'arima'
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Alerts raised when forecasted demand × lead time exceeds stock
CREATE TABLE reorder_alerts (
    alert_id            SERIAL PRIMARY KEY,
    forecast_id         INT REFERENCES demand_forecasts(forecast_id) ON DELETE SET NULL,
    product_id          INT NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    warehouse_id        INT NOT NULL REFERENCES warehouses(warehouse_id) ON DELETE CASCADE,
    supplier_id         INT NOT NULL REFERENCES suppliers(supplier_id) ON DELETE RESTRICT,
    alert_date          DATE NOT NULL DEFAULT CURRENT_DATE,
    suggested_order_qty INT NOT NULL CHECK (suggested_order_qty > 0),
    status              VARCHAR(20) NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','acknowledged','ordered','resolved')),
    resolved_date       DATE
);

-- =============================================================
-- VIEW: available stock (quantity_on_hand - reserved_qty)
-- Computed, never stored → no update anomaly.
-- =============================================================
CREATE VIEW v_available_stock AS
SELECT
    sl.stock_id,
    sl.product_id,
    p.sku,
    p.product_name,
    sl.warehouse_id,
    w.warehouse_name,
    sl.quantity_on_hand,
    sl.reserved_qty,
    (sl.quantity_on_hand - sl.reserved_qty) AS available_qty,
    sl.reorder_point,
    sl.last_updated
FROM stock_levels sl
JOIN products   p ON p.product_id   = sl.product_id
JOIN warehouses w ON w.warehouse_id = sl.warehouse_id;

-- Convenience view: line totals for sales items
CREATE VIEW v_sales_line_totals AS
SELECT
    si.sale_item_id,
    si.sale_id,
    si.product_id,
    si.quantity,
    si.unit_price,
    si.discount,
    (si.quantity * si.unit_price - si.discount) AS line_total
FROM sales_transaction_items si;

-- =============================================================
-- INDEXES on foreign keys and common query columns
-- PK indexes are created automatically; these cover FK look-ups
-- and the dashboard's most frequent filters.
-- =============================================================

-- products
CREATE INDEX idx_products_category  ON products(category_id);
CREATE INDEX idx_products_supplier  ON products(supplier_id);

-- stock_levels (the UNIQUE constraint already indexes product+warehouse)
-- but individual FK indexes help JOIN performance:
CREATE INDEX idx_stock_product      ON stock_levels(product_id);
CREATE INDEX idx_stock_warehouse    ON stock_levels(warehouse_id);

-- sales_transactions: dashboard queries filter by date and warehouse
CREATE INDEX idx_sales_date         ON sales_transactions(sale_date);
CREATE INDEX idx_sales_warehouse    ON sales_transactions(warehouse_id);
CREATE INDEX idx_sales_customer     ON sales_transactions(customer_id);

-- sales_transaction_items: aggregation by product
CREATE INDEX idx_sale_items_sale    ON sales_transaction_items(sale_id);
CREATE INDEX idx_sale_items_product ON sales_transaction_items(product_id);

-- purchase_orders
CREATE INDEX idx_po_supplier        ON purchase_orders(supplier_id);

-- purchase_order_items
CREATE INDEX idx_po_items_po        ON purchase_order_items(po_id);
CREATE INDEX idx_po_items_product   ON purchase_order_items(product_id);

-- demand_forecasts: look-ups by product+warehouse and date
CREATE INDEX idx_forecast_product   ON demand_forecasts(product_id);
CREATE INDEX idx_forecast_warehouse ON demand_forecasts(warehouse_id);
CREATE INDEX idx_forecast_date      ON demand_forecasts(forecast_date);

-- reorder_alerts
CREATE INDEX idx_alert_product      ON reorder_alerts(product_id);
CREATE INDEX idx_alert_warehouse    ON reorder_alerts(warehouse_id);
CREATE INDEX idx_alert_status       ON reorder_alerts(status);

-- =============================================================
-- TRIGGER: prevent stock going negative
-- This fires BEFORE any UPDATE on stock_levels and rejects
-- the change if quantity_on_hand would drop below zero.
-- Why a trigger instead of just the CHECK constraint?
--   The CHECK already prevents storing a negative value, but the
--   trigger gives a clear, custom error message before the row
--   is written, and lets us log or handle the event if needed.
-- =============================================================

CREATE OR REPLACE FUNCTION fn_block_negative_stock()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.quantity_on_hand < 0 THEN
        RAISE EXCEPTION 'Insufficient stock: product_id=%, warehouse_id=%. '
                         'Attempted quantity_on_hand=%',
                         NEW.product_id, NEW.warehouse_id, NEW.quantity_on_hand;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_block_negative_stock
    BEFORE UPDATE ON stock_levels
    FOR EACH ROW
    EXECUTE FUNCTION fn_block_negative_stock();

-- =============================================================
-- STORED PROCEDURES for transactional stock updates
--
-- Why procedures instead of doing it purely in the API layer?
--   1. The deduction/addition + stock_levels update happen in a
--      single server round-trip → less chance of partial failure.
--   2. Business rules (negative-stock block) stay in the DB even
--      if someone runs SQL directly.
--   The API still wraps calls in a transaction for the header +
--   multiple line items, but the per-item stock change is here.
-- =============================================================

-- Deduct stock when a sale line item is recorded.
-- Called once per line item inside the sale transaction.
CREATE OR REPLACE FUNCTION fn_deduct_stock(
    p_product_id   INT,
    p_warehouse_id INT,
    p_qty          INT
) RETURNS VOID AS $$
BEGIN
    UPDATE stock_levels
       SET quantity_on_hand = quantity_on_hand - p_qty,
           last_updated     = now()
     WHERE product_id  = p_product_id
       AND warehouse_id = p_warehouse_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No stock_levels row for product_id=%, warehouse_id=%',
                         p_product_id, p_warehouse_id;
    END IF;
    -- The trg_block_negative_stock trigger fires on the UPDATE above
    -- and will abort if quantity_on_hand would go negative.
END;
$$ LANGUAGE plpgsql;

-- Add stock when a PO line item is received.
CREATE OR REPLACE FUNCTION fn_receive_stock(
    p_product_id   INT,
    p_warehouse_id INT,
    p_qty          INT
) RETURNS VOID AS $$
BEGIN
    -- Upsert: create the stock_levels row if it doesn't exist yet.
    INSERT INTO stock_levels (product_id, warehouse_id, quantity_on_hand, last_updated)
    VALUES (p_product_id, p_warehouse_id, p_qty, now())
    ON CONFLICT (product_id, warehouse_id)
    DO UPDATE SET quantity_on_hand = stock_levels.quantity_on_hand + EXCLUDED.quantity_on_hand,
                  last_updated     = now();
END;
$$ LANGUAGE plpgsql;

COMMIT;
