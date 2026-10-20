"""
StockSense — Phase 2: Synthetic Seed Data Generator
Generates realistic inventory data for ~30 products across 3 warehouses
with 18 months of sales history including weekly/seasonal patterns and
occasional demand spikes.

Run:  python3 db/seed.py > db/seed.sql
Then: psql -U stocksense -d stocksense -f db/seed.sql
"""

import random
import math
from datetime import date, timedelta
from collections import defaultdict

random.seed(42)  # reproducible data

# ─── Reference data ─────────────────────────────────────────────

CATEGORIES = [
    ("Electronics", "Consumer and industrial electronics"),
    ("Office Supplies", "Stationery, paper, and desk accessories"),
    ("Furniture", "Desks, chairs, shelving, and storage"),
    ("Cleaning", "Cleaning chemicals, tools, and supplies"),
    ("Safety", "PPE, first aid, and safety equipment"),
]

SUPPLIERS = [
    ("TechFlow Distributors",   "Ravi Menon",    "ravi@techflow.in",      "+91-9800010001", "Chennai, TN"),
    ("OfficeMart India",        "Priya Sharma",  "priya@officemart.in",   "+91-9800020002", "Mumbai, MH"),
    ("FurniPro Wholesale",      "Arjun Patel",   "arjun@furnipro.in",    "+91-9800030003", "Ahmedabad, GJ"),
    ("CleanCorp Supplies",      "Meena Das",     "meena@cleancorp.in",   "+91-9800040004", "Kolkata, WB"),
    ("SafeGuard Equipment",     "Karthik Nair",  "karthik@safeguard.in", "+91-9800050005", "Bangalore, KA"),
    ("GlobalTech Partners",     "Sneha Reddy",   "sneha@globaltech.in",  "+91-9800060006", "Hyderabad, TS"),
]

WAREHOUSES = [
    ("Central Warehouse", "Mumbai",    "Plot 14, MIDC Andheri East, Mumbai 400093"),
    ("South Hub",         "Chennai",   "Warehouse 7, Ambattur Industrial Estate, Chennai 600058"),
    ("North Depot",       "Delhi NCR", "Sector 63, Noida, UP 201301"),
]

# (name, category_index 1-based, supplier_index 1-based, unit_price, lead_time_days)
PRODUCTS = [
    # Electronics (cat 1)
    ("Wireless Mouse",           1, 1,   599.00,  7),
    ("Mechanical Keyboard",      1, 1,  2499.00,  10),
    ("USB-C Hub 7-port",         1, 1,  1299.00,  10),
    ("27\" LED Monitor",         1, 6,  14999.00, 14),
    ("Webcam 1080p",             1, 6,  2999.00,  10),
    ("Ethernet Cable 3m",        1, 1,   149.00,  5),
    ("Power Strip 6-socket",     1, 1,   499.00,  5),
    # Office Supplies (cat 2)
    ("A4 Paper Ream 500sh",      2, 2,   299.00,  3),
    ("Ballpoint Pen Box 50",     2, 2,   350.00,  3),
    ("Whiteboard Marker Set 4",  2, 2,   180.00,  3),
    ("Sticky Notes 3x3 Pack 12", 2, 2,   220.00,  3),
    ("Binder Clips Box 100",     2, 2,   120.00,  3),
    ("Manila Envelope A4 50pk",  2, 2,   275.00,  3),
    ("Desk Organizer Tray",      2, 2,   450.00,  5),
    # Furniture (cat 3)
    ("Ergonomic Office Chair",   3, 3,  8999.00, 21),
    ("Standing Desk 120cm",      3, 3, 15999.00, 21),
    ("3-Shelf Bookcase",         3, 3,  3499.00, 14),
    ("Filing Cabinet 3-Drawer",  3, 3,  5499.00, 14),
    ("Folding Table 180cm",      3, 3,  2999.00, 14),
    # Cleaning (cat 4)
    ("Floor Cleaner 5L",         4, 4,   399.00,  5),
    ("Glass Cleaner 500ml",      4, 4,   149.00,  5),
    ("Microfiber Cloth Pack 10", 4, 4,   350.00,  5),
    ("Hand Sanitizer 500ml",     4, 4,   199.00,  5),
    ("Trash Bags 50L Roll 30",   4, 4,   250.00,  5),
    # Safety (cat 5)
    ("Safety Goggles",           5, 5,   299.00,  7),
    ("First Aid Kit 50-person",  5, 5,  1499.00, 10),
    ("Fire Extinguisher 2kg",    5, 5,  1899.00, 10),
    ("Hi-Vis Vest",              5, 5,   249.00,  5),
    ("Nitrile Gloves Box 100",   5, 5,   449.00,  5),
    ("Ear Plugs Pack 50",        5, 5,   199.00,  5),
]

CUSTOMERS = [
    ("Acme Corp",           "orders@acme.co.in",       "+91-4400010001", "Chennai"),
    ("Zenith Technologies",  "purchase@zenith.in",      "+91-2200020002", "Mumbai"),
    ("BrightStar Ltd",       "buy@brightstar.co.in",    "+91-1100030003", "Delhi"),
    ("Pinnacle Solutions",   "supply@pinnacle.in",      "+91-8000040004", "Bangalore"),
    ("Nova Enterprises",     "orders@nova.co.in",       "+91-4000050005", "Hyderabad"),
    ("Summit Industries",    "procurement@summit.in",   "+91-3300060006", "Kolkata"),
    ("Atlas Services",       "atlas.orders@atlas.in",   "+91-7900070007", "Pune"),
    ("Horizon Group",        "buying@horizon.co.in",    "+91-4100080008", "Chennai"),
    ("Vertex Retail",        "supply@vertexretail.in",  "+91-2200090009", "Mumbai"),
    ("Quantum Logistics",    "orders@quantumlog.in",    "+91-1200100010", "Noida"),
]

PAYMENT_METHODS = ["cash", "card", "upi", "bank_transfer"]

# ─── Temporal config ────────────────────────────────────────────

START_DATE = date(2025, 4, 1)   # 18 months of history
END_DATE   = date(2026, 9, 30)

# ─── Helpers ────────────────────────────────────────────────────

def esc(s):
    """Escape single quotes for SQL strings."""
    return s.replace("'", "''")

def seasonal_factor(d, product_idx):
    """
    Returns a multiplier (0.5–2.0) based on month.
    Electronics spike in Oct-Dec (festive / year-end budgets).
    Cleaning spikes in Mar-Apr (financial year-end deep cleans).
    Office supplies spike Jul-Aug (back to school/office) & Jan.
    Furniture is steadier but dips in monsoon (Jul-Aug).
    Safety is fairly flat with a small Q1 bump.
    """
    cat = PRODUCTS[product_idx][1]  # category_index
    m = d.month
    if cat == 1:  # Electronics
        return 1.6 if m in (10, 11, 12) else (0.7 if m in (2, 3) else 1.0)
    elif cat == 2:  # Office
        return 1.4 if m in (1, 7, 8) else (0.8 if m in (5, 6) else 1.0)
    elif cat == 3:  # Furniture
        return 0.6 if m in (7, 8) else (1.2 if m in (1, 4, 10) else 1.0)
    elif cat == 4:  # Cleaning
        return 1.5 if m in (3, 4) else 1.0
    else:  # Safety
        return 1.2 if m in (1, 2, 3) else 1.0

def daily_base_demand(product_idx):
    """
    Base average daily units sold.  Cheap consumables sell more;
    expensive furniture sells very little.
    """
    price = PRODUCTS[product_idx][3]
    if price < 300:
        return 3.0
    elif price < 1000:
        return 1.5
    elif price < 5000:
        return 0.6
    elif price < 10000:
        return 0.15
    else:
        return 0.07


# ─── Generate SQL ────────────────────────────────────────────────

lines = []
w = lines.append

w("-- StockSense Phase 2: Seed Data (auto-generated)")
w("-- Run AFTER schema.sql has been applied.")
w("BEGIN;\n")

# Categories
for name, desc in CATEGORIES:
    w(f"INSERT INTO categories (category_name, description) VALUES ('{esc(name)}', '{esc(desc)}');")
w("")

# Suppliers
for s in SUPPLIERS:
    w(f"INSERT INTO suppliers (supplier_name, contact_person, email, phone, address) "
      f"VALUES ('{esc(s[0])}', '{esc(s[1])}', '{esc(s[2])}', '{esc(s[3])}', '{esc(s[4])}');")
w("")

# Warehouses
for wh in WAREHOUSES:
    w(f"INSERT INTO warehouses (warehouse_name, location, address) "
      f"VALUES ('{esc(wh[0])}', '{esc(wh[1])}', '{esc(wh[2])}');")
w("")

# Products
for i, p in enumerate(PRODUCTS):
    sku = f"SS-{i+1:03d}"
    w(f"INSERT INTO products (sku, product_name, category_id, supplier_id, unit_price, lead_time_days) "
      f"VALUES ('{sku}', '{esc(p[0])}', {p[1]}, {p[2]}, {p[3]}, {p[4]});")
w("")

# Customers
for c in CUSTOMERS:
    w(f"INSERT INTO customers (customer_name, email, phone, address) "
      f"VALUES ('{esc(c[0])}', '{esc(c[1])}', '{esc(c[2])}', '{esc(c[3])}');")
w("")

# ─── Generate sales, stock movements, POs ──────────────────────

num_products   = len(PRODUCTS)
num_warehouses = len(WAREHOUSES)
num_customers  = len(CUSTOMERS)

# Track stock per (product_id, warehouse_id) — 1-indexed
stock = {}
for pid in range(1, num_products + 1):
    for wid in range(1, num_warehouses + 1):
        stock[(pid, wid)] = 0

# We'll collect sales and POs, then emit SQL at the end
sale_rows = []          # (sale_date, customer_id, warehouse_id, items_list)
po_rows   = []          # (order_date, supplier_id, expected_date, items_list, receiving_warehouse_id)

# --- Initial POs to seed starting stock (placed 1 month before first sale) ---
initial_po_date = START_DATE - timedelta(days=30)
for supplier_idx in range(1, len(SUPPLIERS) + 1):
    # Find products from this supplier
    supplier_products = [i+1 for i, p in enumerate(PRODUCTS) if p[2] == supplier_idx]
    if not supplier_products:
        continue
    for wid in range(1, num_warehouses + 1):
        items = []
        for pid in supplier_products:
            # Initial stock: enough for ~2-3 months of average demand
            base = daily_base_demand(pid - 1)
            init_qty = max(10, int(base * 75 + random.randint(5, 30)))
            items.append((pid, init_qty, PRODUCTS[pid-1][3] * 0.6))  # unit_cost ≈ 60% of retail
            stock[(pid, wid)] += init_qty
        expected = initial_po_date + timedelta(days=PRODUCTS[supplier_products[0]-1][4])
        po_rows.append((initial_po_date, supplier_idx, expected, items, wid))

# --- Daily sales simulation ---
# Spike days: random big-order days (festivals, bulk buys)
total_days = (END_DATE - START_DATE).days
spike_days = set(random.sample(range(total_days), k=15))  # 15 spike days over 18 months

current_date = START_DATE

# Track cumulative sales for restocking logic
sales_since_last_po = defaultdict(lambda: defaultdict(int))  # supplier -> {(pid,wid): qty}
last_po_date = defaultdict(lambda: initial_po_date)           # supplier -> date

while current_date <= END_DATE:
    day_offset = (current_date - START_DATE).days

    # Weekend effect: lower sales on Sunday
    weekend_factor = 0.3 if current_date.weekday() == 6 else (0.7 if current_date.weekday() == 5 else 1.0)

    # Spike?
    spike = day_offset in spike_days
    spike_factor = random.uniform(2.5, 4.0) if spike else 1.0

    # Generate sales for this day
    # Each sale is from one customer at one warehouse
    num_sales_today = max(0, int(random.gauss(3, 1.2) * weekend_factor * spike_factor))

    for _ in range(num_sales_today):
        cust_id = random.randint(1, num_customers)
        wh_id   = random.randint(1, num_warehouses)

        # Pick 1-5 line items (more during spikes)
        num_items = random.randint(1, 5 if spike else 3)
        chosen_products = random.sample(range(1, num_products + 1), k=min(num_items, num_products))

        items = []
        for pid in chosen_products:
            pidx = pid - 1
            base = daily_base_demand(pidx)
            sf = seasonal_factor(current_date, pidx)
            mean_qty = base * sf * weekend_factor * (spike_factor if spike else 1.0)
            qty = max(1, int(random.gauss(mean_qty, mean_qty * 0.4)))

            # Can't sell more than we have
            available = stock.get((pid, wh_id), 0)
            if available <= 0:
                continue
            qty = min(qty, available)

            price = PRODUCTS[pidx][3]
            # Small random discount (0-10%)
            discount_pct = random.choice([0, 0, 0, 0, 0, 0.05, 0.05, 0.10])
            discount_amt = round(qty * price * discount_pct, 2)

            items.append((pid, qty, price, discount_amt))
            stock[(pid, wh_id)] -= qty
            sales_since_last_po[PRODUCTS[pidx][2]][(pid, wh_id)] += qty

        if items:
            sale_rows.append((current_date, cust_id, wh_id, items))

    # --- Restocking logic: check every 2 weeks per supplier ---
    for sup_id in range(1, len(SUPPLIERS) + 1):
        if (current_date - last_po_date[sup_id]).days >= 14:
            supplier_products = [i+1 for i, p in enumerate(PRODUCTS) if p[2] == sup_id]
            po_items = []
            for wid in range(1, num_warehouses + 1):
                for pid in supplier_products:
                    current_stock = stock.get((pid, wid), 0)
                    sold = sales_since_last_po[sup_id].get((pid, wid), 0)
                    # Reorder if stock < 4 weeks of recent sales rate
                    daily_rate = sold / max(1, (current_date - last_po_date[sup_id]).days)
                    reorder_threshold = daily_rate * 28 + 10
                    if current_stock < reorder_threshold:
                        order_qty = max(10, int(daily_rate * 45) + random.randint(5, 20))
                        cost = round(PRODUCTS[pid-1][3] * random.uniform(0.55, 0.65), 2)
                        po_items.append((pid, order_qty, cost, wid))

            if po_items:
                # Group by warehouse for receiving
                by_wh = defaultdict(list)
                for pid, qty, cost, wid in po_items:
                    by_wh[wid].append((pid, qty, cost))

                for wid, witems in by_wh.items():
                    lead = max(p[4] for i, p in enumerate(PRODUCTS) if p[2] == sup_id)
                    expected = current_date + timedelta(days=lead)
                    # Only receive if expected_date is in the past (or today) relative to simulation
                    receive_date = expected if expected <= END_DATE else None
                    po_rows.append((current_date, sup_id, expected, [(pid, qty, cost) for pid, qty, cost in witems], wid))

                    # Simulate receiving the stock on expected_date
                    if receive_date and receive_date <= END_DATE:
                        for pid, qty, cost in witems:
                            stock[(pid, wid)] += qty

                sales_since_last_po[sup_id] = defaultdict(int)
                last_po_date[sup_id] = current_date

    current_date += timedelta(days=1)

# ─── Emit SQL ───────────────────────────────────────────────────

# Initial stock levels (after all initial POs but before sales)
# We'll compute what starting stock was and use fn_receive_stock via direct INSERT
w("-- Initial stock levels (set by initial POs)")
for pid in range(1, num_products + 1):
    for wid in range(1, num_warehouses + 1):
        # Recalculate initial qty from initial POs
        init_qty = 0
        for po in po_rows:
            if po[0] == initial_po_date and po[4] == wid:
                for item in po[3]:
                    if item[0] == pid:
                        init_qty += item[1]
        if init_qty > 0:
            # Set a reasonable reorder point: ~2 weeks of base demand
            base = daily_base_demand(pid - 1)
            reorder_pt = max(5, int(base * 14))
            w(f"INSERT INTO stock_levels (product_id, warehouse_id, quantity_on_hand, reorder_point) "
              f"VALUES ({pid}, {wid}, {init_qty}, {reorder_pt});")
w("")

# Purchase orders
w("-- Purchase orders")
po_id = 0
for po_date, sup_id, exp_date, items, recv_wid in po_rows:
    po_id += 1
    total = sum(qty * cost for _, qty, cost in items)
    # If expected_date <= END_DATE, mark as received; otherwise ordered
    status = 'received' if exp_date <= END_DATE else 'ordered'
    w(f"INSERT INTO purchase_orders (supplier_id, order_date, expected_date, status, total_amount) "
      f"VALUES ({sup_id}, '{po_date}', '{exp_date}', '{status}', {round(total, 2)});")
    for pid, qty, cost in items:
        recv = qty if status == 'received' else 0
        w(f"INSERT INTO purchase_order_items (po_id, product_id, quantity, unit_cost, received_qty) "
          f"VALUES ({po_id}, {pid}, {qty}, {cost}, {recv});")
w("")

# Sales transactions
w("-- Sales transactions")
sale_id = 0
for sale_date, cust_id, wh_id, items in sale_rows:
    sale_id += 1
    total = sum(qty * price - disc for _, qty, price, disc in items)
    pm = random.choice(PAYMENT_METHODS)
    w(f"INSERT INTO sales_transactions (customer_id, warehouse_id, sale_date, total_amount, payment_method, status) "
      f"VALUES ({cust_id}, {wh_id}, '{sale_date}', {round(total, 2)}, '{pm}', 'completed');")
    for pid, qty, price, disc in items:
        w(f"INSERT INTO sales_transaction_items (sale_id, product_id, quantity, unit_price, discount) "
          f"VALUES ({sale_id}, {pid}, {qty}, {price}, {disc});")
w("")

# Update stock_levels to reflect final state after all sales and PO receipts
# (The initial INSERT set starting stock; we need to adjust to final quantities.)
# Instead of complex updates, we'll just UPDATE to final computed stock values.
w("-- Update stock to final computed values after all sales/PO receipts")
for pid in range(1, num_products + 1):
    for wid in range(1, num_warehouses + 1):
        final_qty = max(0, stock.get((pid, wid), 0))
        w(f"UPDATE stock_levels SET quantity_on_hand = {final_qty}, last_updated = now() "
          f"WHERE product_id = {pid} AND warehouse_id = {wid};")
w("")

w("COMMIT;")
w("")

# ─── Stats ──────────────────────────────────────────────────────

w(f"-- Stats: {len(PRODUCTS)} products, {len(WAREHOUSES)} warehouses, "
  f"{len(SUPPLIERS)} suppliers, {len(CUSTOMERS)} customers")
w(f"-- Stats: {len(sale_rows)} sales transactions, {len(po_rows)} purchase orders")
w(f"-- Stats: Date range: {START_DATE} to {END_DATE} ({total_days} days)")

print("\n".join(lines))
