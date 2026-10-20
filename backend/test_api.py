"""
API tests for StockSense FastAPI backend.
Uses TestClient (Starlette) which runs requests in-process, no server needed.

Usage:  pytest backend/test_api.py -v
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest
from fastapi.testclient import TestClient
from backend.api import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ─── Health ─────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ─── Products ───────────────────────────────────────────────────

def test_list_products(client):
    r = client.get("/products")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 30


def test_get_product(client):
    r = client.get("/products/1")
    assert r.status_code == 200
    assert r.json()["product_id"] == 1


def test_get_product_404(client):
    r = client.get("/products/99999")
    assert r.status_code == 404


def test_create_and_delete_product(client):
    body = {
        "sku": "TEST-API-001",
        "product_name": "API Test Product",
        "category_id": 1,
        "supplier_id": 1,
        "unit_price": 99.99,
        "lead_time_days": 7,
    }
    r = client.post("/products", json=body)
    assert r.status_code == 201
    pid = r.json()["product_id"]

    # Verify it exists
    r = client.get(f"/products/{pid}")
    assert r.status_code == 200
    assert r.json()["sku"] == "TEST-API-001"

    # Delete it
    r = client.delete(f"/products/{pid}")
    assert r.status_code == 200

    # Verify gone
    r = client.get(f"/products/{pid}")
    assert r.status_code == 404


def test_create_duplicate_sku(client):
    """Duplicate SKU should return 409."""
    body = {
        "sku": "SS-001",  # already exists
        "product_name": "Duplicate",
        "category_id": 1,
        "supplier_id": 1,
        "unit_price": 10,
        "lead_time_days": 1,
    }
    r = client.post("/products", json=body)
    assert r.status_code == 409


# ─── Suppliers ──────────────────────────────────────────────────

def test_list_suppliers(client):
    r = client.get("/suppliers")
    assert r.status_code == 200
    assert len(r.json()) >= 6


# ─── Warehouses ─────────────────────────────────────────────────

def test_list_warehouses(client):
    r = client.get("/warehouses")
    assert r.status_code == 200
    assert len(r.json()) >= 3


# ─── Stock Levels ───────────────────────────────────────────────

def test_stock_levels(client):
    r = client.get("/stock-levels")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 90  # 30×3

    # Check computed field
    for row in data[:5]:
        assert "available_qty" in row
        assert row["available_qty"] == row["quantity_on_hand"] - row["reserved_qty"]


def test_stock_levels_filter(client):
    r = client.get("/stock-levels?warehouse_id=1")
    assert r.status_code == 200
    data = r.json()
    assert all(row["warehouse_id"] == 1 for row in data)


# ─── Sales ──────────────────────────────────────────────────────

def test_record_sale(client):
    """Record a small sale and verify stock was deducted."""
    # Get current stock for product 1, warehouse 1
    r = client.get("/stock-levels?warehouse_id=1")
    stock_before = None
    for row in r.json():
        if row["product_id"] == 1:
            stock_before = row["quantity_on_hand"]
            break
    assert stock_before is not None and stock_before > 0

    sale = {
        "customer_id": 1,
        "warehouse_id": 1,
        "payment_method": "card",
        "items": [
            {"product_id": 1, "quantity": 1, "unit_price": 599.00, "discount": 0}
        ]
    }
    r = client.post("/sales", json=sale)
    assert r.status_code == 201
    assert "sale_id" in r.json()

    # Verify stock was deducted
    r = client.get("/stock-levels?warehouse_id=1")
    stock_after = None
    for row in r.json():
        if row["product_id"] == 1:
            stock_after = row["quantity_on_hand"]
            break
    assert stock_after == stock_before - 1


def test_sale_insufficient_stock(client):
    """Trying to sell more than available should return 409."""
    sale = {
        "customer_id": 1,
        "warehouse_id": 1,
        "payment_method": "cash",
        "items": [
            {"product_id": 1, "quantity": 999999, "unit_price": 599.00, "discount": 0}
        ]
    }
    r = client.post("/sales", json=sale)
    assert r.status_code == 409


# ─── PO Receipt ─────────────────────────────────────────────────

def test_receive_po(client):
    """Receive stock against an existing PO."""
    # Get stock before
    r = client.get("/stock-levels?warehouse_id=1")
    stock_before = None
    for row in r.json():
        if row["product_id"] == 1:
            stock_before = row["quantity_on_hand"]
            break

    receive = {
        "po_id": 1,  # first PO from seed
        "warehouse_id": 1,
        "items": [
            {"product_id": 1, "quantity": 5, "unit_cost": 350.00}
        ]
    }
    r = client.post("/purchase-orders/receive", json=receive)
    assert r.status_code == 201
    assert r.json()["items_received"] == 5

    # Verify stock increased
    r = client.get("/stock-levels?warehouse_id=1")
    stock_after = None
    for row in r.json():
        if row["product_id"] == 1:
            stock_after = row["quantity_on_hand"]
            break
    assert stock_after == stock_before + 5


def test_receive_po_not_found(client):
    r = client.post("/purchase-orders/receive", json={
        "po_id": 99999,
        "warehouse_id": 1,
        "items": [{"product_id": 1, "quantity": 1, "unit_cost": 10}]
    })
    assert r.status_code == 404


# ─── Forecasts & Alerts ────────────────────────────────────────

def test_get_forecasts(client):
    r = client.get("/forecasts?product_id=1&warehouse_id=1")
    assert r.status_code == 200
    # May or may not have data depending on whether pipeline was run


def test_get_alerts(client):
    r = client.get("/alerts")
    assert r.status_code == 200


def test_get_sales_history(client):
    r = client.get("/forecasts/history?product_id=1&warehouse_id=1")
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0


# ─── Categories / Customers ────────────────────────────────────

def test_list_categories(client):
    r = client.get("/categories")
    assert r.status_code == 200
    assert len(r.json()) >= 5


def test_list_customers(client):
    r = client.get("/customers")
    assert r.status_code == 200
    assert len(r.json()) >= 10


# ─── Validation ─────────────────────────────────────────────────

def test_sale_validation_422(client):
    """Empty items list should return 422."""
    r = client.post("/sales", json={
        "customer_id": 1,
        "warehouse_id": 1,
        "payment_method": "cash",
        "items": []
    })
    assert r.status_code == 422
