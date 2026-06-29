import os
"""
1. Creates 3 customers with addresses
2. Sets Selling Settings defaults
3. Creates Item Price records (rate=0 placeholder) for all items
   so Sales Order price fields are populated and editable
"""
import requests, json, time

requests.packages.urllib3.disable_warnings()
PROD_URL = "https://www.karavanimports.com"
PASS     = os.environ.get("ERP_ADMIN_PWD")

s = requests.Session(); s.verify = False
s.post(f"{PROD_URL}/api/method/login",
       data={"usr": "Administrator", "pwd": PASS}, timeout=20)
print("Logged in\n")

def POST(path, body):
    return s.post(f"{PROD_URL}{path}", json=body, timeout=30)

def PUT(path, body):
    return s.put(f"{PROD_URL}{path}", json=body, timeout=30)

def uq(v):
    return requests.utils.quote(str(v), safe="")

# ── 1. Customers + Addresses ───────────────────────────────────────────────────
print("[1] Creating Customers...")

CUSTOMERS = [
    {
        "name":    "Slim's Restaurant",
        "type":    "Company",
        "group":   "Commercial",
        "territory": "United States",
        "address_line1": "6901 Brooklyn Boulevard",
        "city":    "Brooklyn Center",
        "state":   "Minnesota",
        "zip":     "55429",
    },
    {
        "name":    "Busy Boys",
        "type":    "Company",
        "group":   "Commercial",
        "territory": "United States",
        "address_line1": "130 Opportunity Blvd",
        "city":    "Cambridge",
        "state":   "Minnesota",
        "zip":     "55008",
    },
    {
        "name":    "Pangea Market & Grill",
        "type":    "Company",
        "group":   "Commercial",
        "territory": "United States",
        "address_line1": "8500 Springbrook Dr",
        "city":    "Coon Rapids",
        "state":   "Minnesota",
        "zip":     "55433",
    },
]

for c in CUSTOMERS:
    # Create customer
    r = POST("/api/resource/Customer", {
        "customer_name":  c["name"],
        "customer_type":  c["type"],
        "customer_group": c["group"],
        "territory":      c["territory"],
    })
    if r.status_code in (200, 201):
        cname = r.json().get("data", {}).get("name", c["name"])
        print(f"  Customer OK: {cname}")
    elif r.status_code == 409 or "already exists" in r.text.lower():
        cname = c["name"]
        print(f"  Customer exists: {cname}")
    else:
        print(f"  Customer ERR {c['name']}: {r.status_code} {r.text[:120]}")
        cname = c["name"]

    # Create billing address
    r2 = POST("/api/resource/Address", {
        "address_title":  c["name"],
        "address_type":   "Billing",
        "address_line1":  c["address_line1"],
        "city":           c["city"],
        "state":          c["state"],
        "pincode":        c["zip"],
        "country":        "United States",
        "is_primary_address": 1,
        "links": [{"link_doctype": "Customer", "link_name": cname}],
    })
    if r2.status_code in (200, 201):
        print(f"  Address  OK: {c['address_line1']}, {c['city']}, MN {c['zip']}")
    else:
        print(f"  Address ERR: {r2.status_code} {r2.text[:120]}")
    time.sleep(0.1)

# ── 2. Selling Settings defaults ───────────────────────────────────────────────
print("\n[2] Setting Selling defaults...")
r = PUT("/api/resource/Selling%20Settings/Selling%20Settings", {
    "selling_price_list":  "Standard Selling",
    "customer_group":      "Commercial",
    "territory":           "United States",
    "cust_master_name":    "Customer Name",
})
print(f"  Selling Settings: {r.status_code}")

# ── 3. Item Prices ─────────────────────────────────────────────────────────────
print("\n[3] Creating Item Price records (Standard Selling, rate=0)...")

# Fetch all items
items = s.get(f"{PROD_URL}/api/resource/Item",
              params={"limit": 500, "fields": '["name","item_name"]'},
              timeout=30).json().get("data", [])
print(f"  {len(items)} items to price")

# Check which already have a price
existing_prices = set()
ep = s.get(f"{PROD_URL}/api/resource/Item%20Price",
           params={"limit": 500, "fields": '["item_code"]',
                   "filters": '[["price_list","=","Standard Selling"]]'},
           timeout=30).json().get("data", [])
for p in ep:
    existing_prices.add(p["item_code"])
print(f"  Already priced: {len(existing_prices)}")

ok = skip = fail = 0
for item in items:
    code = item["name"]
    if code in existing_prices:
        skip += 1
        continue
    r = POST("/api/resource/Item%20Price", {
        "item_code":       code,
        "price_list":      "Standard Selling",
        "selling":         1,
        "currency":        "USD",
        "price_list_rate": 0,
        "uom":             "Nos",
    })
    if r.status_code in (200, 201):
        ok += 1
    else:
        print(f"  ERR {code}: {r.status_code} {r.text[:80]}")
        fail += 1
    time.sleep(0.03)

print(f"  Item Prices: {ok} created, {skip} already existed, {fail} failed")
print("\nDone. Prices are set to $0 — update them via:")
print("  Stock -> Price Lists -> Standard Selling -> Items tab")
