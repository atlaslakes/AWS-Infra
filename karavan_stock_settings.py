import os
"""
Configures ERPNext for inventory-linked invoicing:
1. Stock Settings: Allow Negative Stock = No
2. Stock Settings: set default warehouse
3. Property Setter: Sales Invoice "update_stock" default = 1
"""
import requests

requests.packages.urllib3.disable_warnings()
s = requests.Session(); s.verify = False
s.post("https://www.karavanimports.com/api/method/login",
       data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=20)
print("Logged in\n")

# ── 1. Disable negative stock ─────────────────────────────────────────────────
print("[1] Disabling negative stock...")
r = s.put("https://www.karavanimports.com/api/resource/Stock%20Settings/Stock%20Settings",
          json={"allow_negative_stock": 0}, timeout=20)
print(f"  allow_negative_stock=0 : {r.status_code}")
if r.status_code != 200:
    print(" ", r.text[:200])

# ── 2. Default warehouse ──────────────────────────────────────────────────────
print("\n[2] Fetching warehouses...")
wh_resp = s.get("https://www.karavanimports.com/api/resource/Warehouse",
                params={"fields": '["name","warehouse_type","is_group"]', "limit": 50}, timeout=20)
warehouses = wh_resp.json().get("data", [])
print(f"  Found {len(warehouses)} warehouses:")
for w in warehouses:
    print(f"    {w['name']} (type={w.get('warehouse_type')}, group={w.get('is_group')})")

store_wh = next((w["name"] for w in warehouses
                 if not w.get("is_group") and
                 w.get("warehouse_type") not in ("Transit",) and
                 "transit" not in w["name"].lower()), None)
if store_wh:
    r2 = s.put("https://www.karavanimports.com/api/resource/Stock%20Settings/Stock%20Settings",
               json={"default_warehouse": store_wh}, timeout=20)
    print(f"\n  default_warehouse = {store_wh!r} : {r2.status_code}")
else:
    print("  No suitable leaf warehouse found — set manually in Stock Settings")

# ── 3. Property Setter: update_stock=1 default on Sales Invoice ───────────────
print("\n[3] Setting Sales Invoice update_stock=1 as default...")
existing = s.get("https://www.karavanimports.com/api/resource/Property%20Setter",
                 params={"filters": '[["doc_type","=","Sales Invoice"],["field_name","=","update_stock"],["property","=","default"]]',
                         "fields": '["name"]'}, timeout=20).json().get("data", [])

ps_body = {
    "doctype": "Property Setter",
    "doc_type": "Sales Invoice",
    "doctype_or_field": "DocField",
    "field_name": "update_stock",
    "property": "default",
    "property_type": "Check",
    "value": "1",
    "is_system_generated": 0,
}
if existing:
    name = existing[0]["name"]
    r3 = s.put(f"https://www.karavanimports.com/api/resource/Property%20Setter/{requests.utils.quote(name, safe='')}",
               json=ps_body, timeout=20)
    print(f"  Updated existing Property Setter : {r3.status_code}")
else:
    r3 = s.post("https://www.karavanimports.com/api/resource/Property%20Setter",
                json=ps_body, timeout=20)
    print(f"  Created Property Setter : {r3.status_code}")
if r3.status_code not in (200, 201):
    print(" ", r3.text[:300])

print("\nDone.")
print("  → New Sales Invoices will have 'Update Stock' checked by default")
print("  → Submitting an invoice with insufficient stock will be blocked")
