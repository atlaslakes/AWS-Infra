"""
ERPNext customer/pricing structure:
  - Internal: Pangea A, B, C  → Retail price (no discount)
  - External: Tier dropdown on customer form
      Tier 1 = 20% off  (Tier-1 price list)
      Tier 2 = 10% off  (Tier-2 price list)
      Tier 3 = no discount (Tier-3 price list, default external)
  - Custom Field: Customer.custom_tier (Select dropdown)
"""

import requests
import json
from datetime import date, timedelta

ERPNEXT_URL = "http://atlaslakeserp"
S = requests.Session()
S.headers.update({"Authorization": "token 647f56b706a1bea:6c615d3ea8cbd4d"})

def exists(doctype, name):
    r = S.get(f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(str(name))}", timeout=15)
    return r.status_code == 200

def create(doctype, doc):
    r = S.post(f"{ERPNEXT_URL}/api/resource/{doctype}", json=doc, timeout=20)
    if r.status_code in (200, 201):
        return r.json()["data"]
    raise RuntimeError(f"{doctype} create failed {r.status_code}: {r.text[:400]}")

def get_or_create(doctype, name, doc):
    if exists(doctype, name):
        print(f"  exists : {doctype} / {name}")
        return
    create(doctype, doc)
    print(f"  created: {doctype} / {name}")

def upsert(doctype, name, doc):
    if exists(doctype, name):
        r = S.put(f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(str(name))}", json=doc, timeout=20)
        print(f"  updated: {doctype} / {name}")
        return r.json().get("data")
    else:
        result = create(doctype, doc)
        print(f"  created: {doctype} / {name}")
        return result

# ── 1. Customer Groups ────────────────────────────────────────────────────────
print("\n=== Customer Groups ===")
for grp in ["Internal", "External"]:
    get_or_create("Customer Group", grp, {
        "doctype": "Customer Group",
        "customer_group_name": grp,
        "parent_customer_group": "All Customer Groups",
    })

# ── 2. Price Lists ────────────────────────────────────────────────────────────
print("\n=== Price Lists ===")
price_lists = {
    "Retail": 1.00,  # Pangea A/B/C — full price
    "Tier-1": 0.80,  # External Tier 1 — 20% off
    "Tier-2": 0.90,  # External Tier 2 — 10% off
    "Tier-3": 1.00,  # External Tier 3 — no discount (default)
}
for pl_name in price_lists:
    get_or_create("Price List", pl_name, {
        "doctype": "Price List",
        "price_list_name": pl_name,
        "currency": "USD",
        "selling": 1,
        "buying": 0,
        "enabled": 1,
    })

# ── 3. Internal Customers → Retail (no discount) ──────────────────────────────
print("\n=== Internal Customers (Pangea A/B/C) ===")
for name in ["Pangea A", "Pangea B", "Pangea C"]:
    upsert("Customer", name, {
        "doctype": "Customer",
        "customer_name": name,
        "customer_group": "Internal",
        "customer_type": "Company",
        "default_price_list": "Retail",
    })

# ── 4. Custom Field: Tier dropdown on Customer ────────────────────────────────
print("\n=== Custom Field: Customer Tier ===")
cf_name = "Customer-custom_tier"
get_or_create("Custom Field", cf_name, {
    "doctype": "Custom Field",
    "dt": "Customer",
    "label": "Tier",
    "fieldname": "custom_tier",
    "fieldtype": "Select",
    "options": "\nTier 1\nTier 2\nTier 3",
    "insert_after": "customer_group",
    "description": "Tier 1 = 20% off | Tier 2 = 10% off | Tier 3 = no discount (default)",
    "in_list_view": 1,
})

# ── 5. External Customers (sample, one per tier) ──────────────────────────────
print("\n=== External Customers ===")
tier_pl = {"Tier 1": "Tier-1", "Tier 2": "Tier-2", "Tier 3": "Tier-3"}
ext_customers = [
    {"name": "Walk-in Customer", "tier": "Tier 3"},
    {"name": "External Tier 1",  "tier": "Tier 1"},
    {"name": "External Tier 2",  "tier": "Tier 2"},
]
for c in ext_customers:
    upsert("Customer", c["name"], {
        "doctype": "Customer",
        "customer_name": c["name"],
        "customer_group": "External",
        "customer_type": "Individual",
        "default_price_list": tier_pl[c["tier"]],
        "custom_tier": c["tier"],
    })

# ── 6. Item Prices for each price list ────────────────────────────────────────
print("\n=== Item Prices ===")
r = S.get(f"{ERPNEXT_URL}/api/resource/Item",
          params={"fields": '["item_code","item_name","standard_rate"]', "limit_page_length": 5},
          timeout=15)
sample_items = r.json()["data"][:3]
print(f"  Sample items: {[i['item_code'] for i in sample_items]}")

for item in sample_items:
    base = float(item.get("standard_rate") or 0) or 10.0
    for pl_name, mult in price_lists.items():
        price = round(base * mult, 2)
        check = S.get(f"{ERPNEXT_URL}/api/resource/Item Price",
                      params={"filters": json.dumps([["item_code","=",item["item_code"]],
                                                     ["price_list","=",pl_name]]),
                              "fields": '["name"]'}, timeout=10)
        existing = check.json().get("data", [])
        if existing:
            S.put(f"{ERPNEXT_URL}/api/resource/Item Price/{existing[0]['name']}",
                  json={"price_list_rate": price}, timeout=15)
            print(f"  updated: {item['item_code']} / {pl_name} = ${price}")
        else:
            create("Item Price", {"doctype": "Item Price", "item_code": item["item_code"],
                                  "price_list": pl_name, "price_list_rate": price, "selling": 1})
            print(f"  created: {item['item_code']} / {pl_name} = ${price}")

# ── 7. Sales Orders (one per customer) ───────────────────────────────────────
print("\n=== Sales Orders ===")
today = str(date.today())
delivery_date = str(date.today() + timedelta(days=7))

so_customers = [
    {"name": "Pangea A",        "price_list": "Retail"},
    {"name": "Pangea B",        "price_list": "Retail"},
    {"name": "Pangea C",        "price_list": "Retail"},
    {"name": "External Tier 1", "price_list": "Tier-1"},
    {"name": "External Tier 2", "price_list": "Tier-2"},
    {"name": "Walk-in Customer","price_list": "Tier-3"},
]
for c in so_customers:
    mult = price_lists[c["price_list"]]
    items_payload = [{
        "doctype": "Sales Order Item",
        "item_code": i["item_code"],
        "item_name": i["item_name"],
        "qty": 10,
        "rate": round((float(i.get("standard_rate") or 0) or 10.0) * mult, 2),
        "delivery_date": delivery_date,
    } for i in sample_items]
    try:
        so = create("Sales Order", {
            "doctype": "Sales Order",
            "customer": c["name"],
            "transaction_date": today,
            "delivery_date": delivery_date,
            "selling_price_list": c["price_list"],
            "currency": "USD",
            "set_warehouse": "Stores - LD",
            "items": items_payload,
        })
        print(f"  SO: {so['name']}  →  {c['name']} ({c['price_list']})")
    except RuntimeError as e:
        print(f"  FAILED {c['name']}: {e}")

print("""
=== Done ===
Internal  : Pangea A / B / C  → Retail (full price, no discount)
External  : assign Tier in customer form
            Tier 1 = 20% off | Tier 2 = 10% off | Tier 3 = no discount
Tier field: Customer form → 'Tier' dropdown (below Customer Group)
""")
