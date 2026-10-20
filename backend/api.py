"""
StockSense — FastAPI REST API

Endpoints:
  Products:    GET/POST /products, GET/PUT/DELETE /products/{id}
  Suppliers:   GET/POST /suppliers, GET/PUT/DELETE /suppliers/{id}
  Warehouses:  GET/POST /warehouses, GET/PUT/DELETE /warehouses/{id}
  Sales:       POST /sales (records sale + deducts stock)
  PO Receipt:  POST /purchase-orders/receive (receives PO + adds stock)
  Stock:       GET /stock-levels
  Forecasts:   GET /forecasts, POST /forecasts/run (trigger pipeline)
  Alerts:      GET /alerts, PATCH /alerts/{id}
"""

import sys
import os
import json
import math
from datetime import date
from typing import Optional, List
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
import psycopg2.extras

# ─── App setup ──────────────────────────────────────────────────

app = FastAPI(title="StockSense API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # React dev server on any port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── DB helpers ─────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "stocksense"),
        user=os.getenv("DB_USER", "stocksense"),
        password=os.getenv("DB_PASS", "stocksense123"),
    )


@contextmanager
def db_cursor(commit=False):
    """Context manager yielding a dict-cursor; auto-closes and optionally commits."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur, conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Pydantic models ────────────────────────────────────────────

class ProductCreate(BaseModel):
    sku: str = Field(max_length=50)
    product_name: str = Field(max_length=200)
    description: Optional[str] = None
    category_id: int
    supplier_id: int
    unit_price: float = Field(ge=0)
    lead_time_days: int = Field(ge=0)

class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    unit_price: Optional[float] = Field(default=None, ge=0)
    lead_time_days: Optional[int] = Field(default=None, ge=0)

class SupplierCreate(BaseModel):
    supplier_name: str = Field(max_length=200)
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class SupplierUpdate(BaseModel):
    supplier_name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class WarehouseCreate(BaseModel):
    warehouse_name: str = Field(max_length=200)
    location: Optional[str] = None
    address: Optional[str] = None

class WarehouseUpdate(BaseModel):
    warehouse_name: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None

class SaleItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)
    discount: float = Field(default=0, ge=0)

class SaleCreate(BaseModel):
    customer_id: int
    warehouse_id: int
    payment_method: str = Field(default="cash")
    items: List[SaleItem] = Field(min_length=1)

class POReceiveItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_cost: float = Field(ge=0)

class POReceive(BaseModel):
    po_id: int
    warehouse_id: int
    items: List[POReceiveItem] = Field(min_length=1)

class AlertUpdate(BaseModel):
    status: str = Field(pattern=r"^(open|acknowledged|ordered|resolved)$")


# ─── Products CRUD ──────────────────────────────────────────────

@app.get("/products")
def list_products():
    with db_cursor() as (cur, _):
        cur.execute("""
            SELECT p.*, c.category_name, s.supplier_name
            FROM products p
            JOIN categories c ON c.category_id = p.category_id
            JOIN suppliers s ON s.supplier_id = p.supplier_id
            ORDER BY p.product_id
        """)
        return cur.fetchall()


@app.get("/products/{product_id}")
def get_product(product_id: int):
    with db_cursor() as (cur, _):
        cur.execute("""
            SELECT p.*, c.category_name, s.supplier_name
            FROM products p
            JOIN categories c ON c.category_id = p.category_id
            JOIN suppliers s ON s.supplier_id = p.supplier_id
            WHERE p.product_id = %s
        """, (product_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"Product {product_id} not found")
        return row


@app.post("/products", status_code=201)
def create_product(body: ProductCreate):
    with db_cursor(commit=True) as (cur, _):
        try:
            cur.execute("""
                INSERT INTO products (sku, product_name, description, category_id, supplier_id, unit_price, lead_time_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING product_id
            """, (body.sku, body.product_name, body.description,
                  body.category_id, body.supplier_id, body.unit_price, body.lead_time_days))
            return {"product_id": cur.fetchone()["product_id"]}
        except psycopg2.IntegrityError as e:
            raise HTTPException(409, str(e))


@app.put("/products/{product_id}")
def update_product(product_id: int, body: ProductUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(422, "No fields to update")
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [product_id]
    with db_cursor(commit=True) as (cur, _):
        cur.execute(f"UPDATE products SET {set_clause} WHERE product_id = %s RETURNING product_id", values)
        if not cur.fetchone():
            raise HTTPException(404, f"Product {product_id} not found")
        return {"updated": product_id}


@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    with db_cursor(commit=True) as (cur, _):
        try:
            cur.execute("DELETE FROM products WHERE product_id = %s RETURNING product_id", (product_id,))
            if not cur.fetchone():
                raise HTTPException(404, f"Product {product_id} not found")
            return {"deleted": product_id}
        except psycopg2.IntegrityError as e:
            raise HTTPException(409, f"Cannot delete: {e}")


# ─── Suppliers CRUD ─────────────────────────────────────────────

@app.get("/suppliers")
def list_suppliers():
    with db_cursor() as (cur, _):
        cur.execute("SELECT * FROM suppliers ORDER BY supplier_id")
        return cur.fetchall()


@app.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: int):
    with db_cursor() as (cur, _):
        cur.execute("SELECT * FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"Supplier {supplier_id} not found")
        return row


@app.post("/suppliers", status_code=201)
def create_supplier(body: SupplierCreate):
    with db_cursor(commit=True) as (cur, _):
        cur.execute("""
            INSERT INTO suppliers (supplier_name, contact_person, email, phone, address)
            VALUES (%s, %s, %s, %s, %s) RETURNING supplier_id
        """, (body.supplier_name, body.contact_person, body.email, body.phone, body.address))
        return {"supplier_id": cur.fetchone()["supplier_id"]}


@app.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(422, "No fields to update")
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [supplier_id]
    with db_cursor(commit=True) as (cur, _):
        cur.execute(f"UPDATE suppliers SET {set_clause} WHERE supplier_id = %s RETURNING supplier_id", values)
        if not cur.fetchone():
            raise HTTPException(404, f"Supplier {supplier_id} not found")
        return {"updated": supplier_id}


@app.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: int):
    with db_cursor(commit=True) as (cur, _):
        try:
            cur.execute("DELETE FROM suppliers WHERE supplier_id = %s RETURNING supplier_id", (supplier_id,))
            if not cur.fetchone():
                raise HTTPException(404, f"Supplier {supplier_id} not found")
            return {"deleted": supplier_id}
        except psycopg2.IntegrityError as e:
            raise HTTPException(409, f"Cannot delete: {e}")


# ─── Warehouses CRUD ────────────────────────────────────────────

@app.get("/warehouses")
def list_warehouses():
    with db_cursor() as (cur, _):
        cur.execute("SELECT * FROM warehouses ORDER BY warehouse_id")
        return cur.fetchall()


@app.get("/warehouses/{warehouse_id}")
def get_warehouse(warehouse_id: int):
    with db_cursor() as (cur, _):
        cur.execute("SELECT * FROM warehouses WHERE warehouse_id = %s", (warehouse_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"Warehouse {warehouse_id} not found")
        return row


@app.post("/warehouses", status_code=201)
def create_warehouse(body: WarehouseCreate):
    with db_cursor(commit=True) as (cur, _):
        try:
            cur.execute("""
                INSERT INTO warehouses (warehouse_name, location, address)
                VALUES (%s, %s, %s) RETURNING warehouse_id
            """, (body.warehouse_name, body.location, body.address))
            return {"warehouse_id": cur.fetchone()["warehouse_id"]}
        except psycopg2.IntegrityError as e:
            raise HTTPException(409, str(e))


@app.put("/warehouses/{warehouse_id}")
def update_warehouse(warehouse_id: int, body: WarehouseUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(422, "No fields to update")
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [warehouse_id]
    with db_cursor(commit=True) as (cur, _):
        cur.execute(f"UPDATE warehouses SET {set_clause} WHERE warehouse_id = %s RETURNING warehouse_id", values)
        if not cur.fetchone():
            raise HTTPException(404, f"Warehouse {warehouse_id} not found")
        return {"updated": warehouse_id}


@app.delete("/warehouses/{warehouse_id}")
def delete_warehouse(warehouse_id: int):
    with db_cursor(commit=True) as (cur, _):
        try:
            cur.execute("DELETE FROM warehouses WHERE warehouse_id = %s RETURNING warehouse_id", (warehouse_id,))
            if not cur.fetchone():
                raise HTTPException(404, f"Warehouse {warehouse_id} not found")
            return {"deleted": warehouse_id}
        except psycopg2.IntegrityError as e:
            raise HTTPException(409, f"Cannot delete: {e}")


# ─── Sales ──────────────────────────────────────────────────────

@app.post("/sales", status_code=201)
def record_sale(body: SaleCreate):
    """
    Records a sale and deducts stock atomically.
    Uses fn_deduct_stock() which triggers trg_block_negative_stock.
    Returns 409 if any item has insufficient stock.
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Calculate total
        total = sum(item.quantity * item.unit_price - item.discount for item in body.items)

        # Insert sale header
        cur.execute("""
            INSERT INTO sales_transactions (customer_id, warehouse_id, sale_date, total_amount, payment_method, status)
            VALUES (%s, %s, CURRENT_DATE, %s, %s, 'completed')
            RETURNING sale_id
        """, (body.customer_id, body.warehouse_id, round(total, 2), body.payment_method))
        sale_id = cur.fetchone()["sale_id"]

        # Insert line items and deduct stock
        for item in body.items:
            cur.execute("""
                INSERT INTO sales_transaction_items (sale_id, product_id, quantity, unit_price, discount)
                VALUES (%s, %s, %s, %s, %s)
            """, (sale_id, item.product_id, item.quantity, item.unit_price, item.discount))

            # Deduct stock via stored function (trigger guards negative)
            try:
                cur.execute("SELECT fn_deduct_stock(%s, %s, %s)",
                            (item.product_id, body.warehouse_id, item.quantity))
            except psycopg2.errors.RaiseException as e:
                conn.rollback()
                raise HTTPException(409, f"Insufficient stock: {e}")

        conn.commit()
        return {"sale_id": sale_id, "total_amount": round(total, 2)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()


# ─── PO Receipt ─────────────────────────────────────────────────

@app.post("/purchase-orders/receive", status_code=201)
def receive_po(body: POReceive):
    """
    Receives items against a PO and adds stock via fn_receive_stock().
    Creates a new PO if po_id=0 (for simple receiving without prior PO).
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Verify PO exists
        cur.execute("SELECT po_id, supplier_id FROM purchase_orders WHERE po_id = %s", (body.po_id,))
        po = cur.fetchone()
        if not po:
            raise HTTPException(404, f"PO {body.po_id} not found")

        total_received = 0
        for item in body.items:
            # Add stock via stored function
            cur.execute("SELECT fn_receive_stock(%s, %s, %s)",
                        (item.product_id, body.warehouse_id, item.quantity))

            # Update PO item received_qty
            cur.execute("""
                UPDATE purchase_order_items
                SET received_qty = received_qty + %s
                WHERE po_id = %s AND product_id = %s
            """, (item.quantity, body.po_id, item.product_id))
            total_received += item.quantity

        # Update PO status
        cur.execute("""
            UPDATE purchase_orders SET status = 'received'
            WHERE po_id = %s
        """, (body.po_id,))

        conn.commit()
        return {"po_id": body.po_id, "items_received": total_received}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()


# ─── Stock Levels ───────────────────────────────────────────────

@app.get("/stock-levels")
def get_stock_levels(warehouse_id: Optional[int] = None, low_stock_only: bool = False):
    """
    Returns stock levels with available_qty computed from the view.
    Optional filters: warehouse_id, low_stock_only (available ≤ reorder_point).
    """
    with db_cursor() as (cur, _):
        sql = """
            SELECT v.*, p.lead_time_days, p.supplier_id, s.supplier_name, c.category_name
            FROM v_available_stock v
            JOIN products p ON p.product_id = v.product_id
            JOIN suppliers s ON s.supplier_id = p.supplier_id
            JOIN categories c ON c.category_id = p.category_id
            WHERE 1=1
        """
        params = []
        if warehouse_id:
            sql += " AND v.warehouse_id = %s"
            params.append(warehouse_id)
        if low_stock_only:
            sql += " AND v.available_qty <= v.reorder_point"
        sql += " ORDER BY v.available_qty ASC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        # Convert datetime and date objects to strings for JSON
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows


# ─── Forecasts ──────────────────────────────────────────────────

@app.get("/forecasts")
def get_forecasts(product_id: Optional[int] = None, warehouse_id: Optional[int] = None):
    with db_cursor() as (cur, _):
        sql = """
            SELECT df.*, p.product_name, p.sku, w.warehouse_name
            FROM demand_forecasts df
            JOIN products p ON p.product_id = df.product_id
            JOIN warehouses w ON w.warehouse_id = df.warehouse_id
            WHERE 1=1
        """
        params = []
        if product_id:
            sql += " AND df.product_id = %s"
            params.append(product_id)
        if warehouse_id:
            sql += " AND df.warehouse_id = %s"
            params.append(warehouse_id)
        sql += " ORDER BY df.product_id, df.warehouse_id, df.forecast_date"
        cur.execute(sql, params)
        rows = cur.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows


@app.get("/forecasts/history")
def get_sales_history(product_id: int, warehouse_id: int):
    """Returns daily sales history for charting (actual vs predicted)."""
    with db_cursor() as (cur, _):
        cur.execute("""
            SELECT st.sale_date, SUM(si.quantity) AS daily_qty
            FROM sales_transaction_items si
            JOIN sales_transactions st ON st.sale_id = si.sale_id
            WHERE si.product_id = %s AND st.warehouse_id = %s AND st.status = 'completed'
            GROUP BY st.sale_date
            ORDER BY st.sale_date
        """, (product_id, warehouse_id))
        rows = cur.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows


@app.post("/forecasts/run")
def trigger_forecast():
    """Trigger a full forecast run. Returns summary stats."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.forecasting.pipeline import run_forecast
    conn = get_conn()
    try:
        stats = run_forecast(conn)
        return stats
    finally:
        conn.close()


# ─── Alerts ─────────────────────────────────────────────────────

@app.get("/alerts")
def get_alerts(status: Optional[str] = None):
    with db_cursor() as (cur, _):
        sql = """
            SELECT ra.*, p.product_name, p.sku, w.warehouse_name, s.supplier_name
            FROM reorder_alerts ra
            JOIN products p ON p.product_id = ra.product_id
            JOIN warehouses w ON w.warehouse_id = ra.warehouse_id
            JOIN suppliers s ON s.supplier_id = ra.supplier_id
            WHERE 1=1
        """
        params = []
        if status:
            sql += " AND ra.status = %s"
            params.append(status)
        sql += " ORDER BY ra.alert_date DESC, ra.alert_id DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows


@app.patch("/alerts/{alert_id}")
def update_alert(alert_id: int, body: AlertUpdate):
    with db_cursor(commit=True) as (cur, _):
        resolved_date = "CURRENT_DATE" if body.status == "resolved" else "NULL"
        cur.execute(f"""
            UPDATE reorder_alerts
            SET status = %s, resolved_date = {resolved_date}
            WHERE alert_id = %s
            RETURNING alert_id
        """, (body.status, alert_id))
        if not cur.fetchone():
            raise HTTPException(404, f"Alert {alert_id} not found")
        return {"updated": alert_id, "status": body.status}


# ─── Categories (read-only, for dropdowns) ──────────────────────

@app.get("/categories")
def list_categories():
    with db_cursor() as (cur, _):
        cur.execute("SELECT * FROM categories ORDER BY category_id")
        return cur.fetchall()


# ─── Customers (read-only, for dropdowns) ───────────────────────

@app.get("/customers")
def list_customers():
    with db_cursor() as (cur, _):
        cur.execute("SELECT * FROM customers ORDER BY customer_id")
        return cur.fetchall()


# ─── Purchase Orders (read-only listing) ────────────────────────

@app.get("/purchase-orders")
def list_purchase_orders():
    with db_cursor() as (cur, _):
        cur.execute("""
            SELECT po.*, s.supplier_name
            FROM purchase_orders po
            JOIN suppliers s ON s.supplier_id = po.supplier_id
            ORDER BY po.order_date DESC
        """)
        rows = cur.fetchall()
        for row in rows:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
        return rows


# ─── Health check ───────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(503, str(e))
