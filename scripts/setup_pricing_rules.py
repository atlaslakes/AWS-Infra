"""
Creates ERPNext Pricing Rules so discounts are applied automatically on Sales Orders:
  Tier-1 price list → 20% off
  Tier-2 price list → 10% off
  Tier-3 price list →  0% off (no discount, standard rate)
"""

import requests

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

rules = [
    {"name": "Tier 1 - 20% Discount", "price_list": "Tier-1", "discount": 20},
    {"name": "Tier 2 - 10% Discount", "price_list": "Tier-2", "discount": 10},
]

print("\n=== Pricing Rules ===")
for rule in rules:
    if exists("Pricing Rule", rule["name"]):
        print(f"  exists : {rule['name']}")
        continue
    create("Pricing Rule", {
        "doctype": "Pricing Rule",
        "title": rule["name"],
        "apply_on": "Transaction",
        "price_or_product_discount": "Price",
        "selling": 1,
        "buying": 0,
        "for_price_list": rule["price_list"],
        "rate_or_discount": "Discount Percentage",
        "discount_percentage": rule["discount"],
        "priority": 1,
        "currency": "USD",
        "enabled": 1,
    })
    print(f"  created: {rule['name']} ({rule['discount']}% off when using {rule['price_list']})")

print("""
=== Done ===
Now when you create a Sales Order for a Tier 1 customer:
  → ERPNext automatically applies 20% off every item
For Tier 2 → 10% off every item
For Tier 3 / Retail → no discount (standard price)
""")
