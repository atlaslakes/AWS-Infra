import os
"""
NOTE: the "Sync Item Cost - Bin" script this file creates is SUPERSEDED
by setup_stock_price_scheduled_sync.py and is now disabled on the live
site (the Stock Ledger Entry hook it used turned out unreliable around
cancellation). "Sync Item Price - Margin Change" below is unaffected
and still active -- editing a Pricing Rule is a normal doc.save().

Wires Item selling price to Item cost via a per-item, customizable margin —
using only native ERPNext fields (no Custom Fields):

  Cost            Item.valuation_rate, synced from Bin.valuation_rate
                  (weighted average across warehouses)
  Margin          Pricing Rule "Margin - <item_code>" (one per item),
                  margin_type (Percentage/Amount) + margin_rate_or_amount
  Selling price   Item Price (price_list="Standard Selling"), price_list_rate,
                  recomputed as cost (op) margin

Creates two Server Scripts so both sides stay live:
  1. "Sync Item Cost - Bin" (Stock Ledger Entry, After Insert) — stock
     moved -> cost changed -> re-derive selling price.
  2. "Sync Item Price - Margin Change" (Pricing Rule, After Save) — margin
     edited -> re-derive selling price from the item's current cost.

Script 1 is hooked on Stock Ledger Entry, not Bin: every real stock
movement (Sales Invoice with Update Stock, Stock Reconciliation, Stock
Entry, ...) updates Bin.actual_qty/valuation_rate via internal bulk SQL,
which never fires a Bin "After Save" hook. A Stock Ledger Entry is
always created through the ORM (insert()), so it's the one doctype
event that reliably fires for every stock-affecting transaction.

Prerequisite (already run once): Item.valuation_rate / Bin.valuation_rate
seeded from the prior Item Price values, and one "Margin - <item_code>"
Pricing Rule per item created at 0% margin (selling = cost until adjusted).

Run once against the site:
    ERP_ADMIN_USR=... ERP_ADMIN_PWD=... python setup_cost_margin_pricing.py
"""

import requests, sys
requests.packages.urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
s = requests.Session(); s.verify = False

login_resp = s.post(f"{URL}/api/method/login",
                     data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"),
                           "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
if login_resp.status_code != 200:
    print(f"Login failed {login_resp.status_code}: {login_resp.text[:300]}")
    sys.exit(1)

def q(n): return requests.utils.quote(str(n), safe="")

def exists(dt, name):
    return s.get(f"{URL}/api/resource/{q(dt)}/{q(name)}", timeout=10).status_code == 200

def create(dt, doc):
    r = s.post(f"{URL}/api/resource/{q(dt)}", json=doc, timeout=20)
    if r.status_code in (200, 201): return r.json()["data"]
    raise RuntimeError(f"CREATE {dt} failed {r.status_code}: {r.text[:300]}")

def update(dt, name, doc):
    r = s.put(f"{URL}/api/resource/{q(dt)}/{q(name)}", json=doc, timeout=20)
    if r.status_code in (200, 201): return r.json()["data"]
    raise RuntimeError(f"UPDATE {dt}/{name} failed {r.status_code}: {r.text[:300]}")

def upsert(dt, name, doc):
    if exists(dt, name):
        update(dt, name, doc)
        print(f"  updated : {dt} / {name}")
    else:
        create(dt, doc)
        print(f"  created : {dt} / {name}")


_UPSERT_ITEM_PRICE = """
def upsert_selling_price(item_code, new_price):
    existing = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": "Standard Selling", "selling": 1},
        "name",
    )
    if existing:
        frappe.db.set_value("Item Price", existing, "price_list_rate", new_price, update_modified=False)
    else:
        frappe.get_doc({
            "doctype": "Item Price",
            "item_code": item_code,
            "price_list": "Standard Selling",
            "selling": 1,
            "price_list_rate": new_price,
        }).insert(ignore_permissions=True)
"""

bin_sync_script = _UPSERT_ITEM_PRICE + """
rows = frappe.db.sql('''
    SELECT sle.qty_after_transaction AS qty, sle.valuation_rate AS rate
    FROM `tabStock Ledger Entry` sle
    INNER JOIN (
        SELECT warehouse, MAX(creation) AS max_creation
        FROM `tabStock Ledger Entry`
        WHERE item_code=%s
        GROUP BY warehouse
    ) latest ON latest.warehouse = sle.warehouse AND latest.max_creation = sle.creation
    WHERE sle.item_code=%s
''', (doc.item_code, doc.item_code), as_dict=True)

paired = [(r.qty or 0, r.rate or 0) for r in rows if (r.qty or 0) > 0]
total_qty = sum(q for q, r in paired)
cost = (sum(q * r for q, r in paired) / total_qty) if total_qty else 0
if cost > 0:
    frappe.db.set_value("Item", doc.item_code, "valuation_rate", cost, update_modified=False)

    rule = frappe.db.get_value(
        "Pricing Rule", {"title": f"Margin - {doc.item_code}"},
        ["margin_type", "margin_rate_or_amount"], as_dict=True
    )
    if rule and rule.margin_type:
        margin = rule.margin_rate_or_amount or 0
        new_price = cost * (1 + margin / 100) if rule.margin_type == "Percentage" else cost + margin
        upsert_selling_price(doc.item_code, new_price)
"""

margin_sync_script = _UPSERT_ITEM_PRICE + """
if doc.margin_type:
    margin = doc.margin_rate_or_amount or 0
    for row in (doc.get("items") or []):
        cost = frappe.db.get_value("Item", row.item_code, "valuation_rate") or 0
        if cost <= 0:
            continue
        new_price = cost * (1 + margin / 100) if doc.margin_type == "Percentage" else cost + margin
        upsert_selling_price(row.item_code, new_price)
"""

print("=== Server Scripts: cost <-> margin <-> selling price sync ===")

upsert("Server Script", "Sync Item Cost - Bin", {
    "doctype": "Server Script",
    "name": "Sync Item Cost - Bin",
    "script_type": "DocType Event",
    "reference_doctype": "Stock Ledger Entry",
    "doctype_event": "After Insert",
    "enabled": 1,
    "script": bin_sync_script,
})

upsert("Server Script", "Sync Item Price - Margin Change", {
    "doctype": "Server Script",
    "name": "Sync Item Price - Margin Change",
    "script_type": "DocType Event",
    "reference_doctype": "Pricing Rule",
    "doctype_event": "After Save",
    "enabled": 1,
    "script": margin_sync_script,
})

print("\nDone.")
