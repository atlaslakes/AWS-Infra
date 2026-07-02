import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Sample items
r = s.get(f"{URL}/api/resource/Item",
          params={"fields": '["name","item_code","item_name","brand","item_group","standard_rate"]',
                  "limit": 5}, timeout=15)
items = r.json().get("data", [])
print("=== Sample Items ===")
for i in items:
    print(json.dumps(i))

# Full first item to see all fields
r2 = s.get(f"{URL}/api/resource/Item/{requests.utils.quote(items[0]['name'])}", timeout=15)
full = r2.json().get("data", {})
print("\n=== Full first item keys ===")
for k, v in full.items():
    if v and k not in ("description", "item_defaults", "taxes", "uoms", "barcodes", "reorder_levels", "website_content"):
        print(f"  {k}: {v}")

# Custom fields on Item
cf = s.get(f"{URL}/api/resource/Custom Field",
           params={"fields": '["fieldname","label","fieldtype"]',
                   "filters": '[["dt","=","Item"]]', "limit": 50}, timeout=15)
print("\n=== Custom Fields on Item ===")
for f in cf.json().get("data", []):
    print(f"  {f['fieldname']} ({f['label']}) - {f['fieldtype']}")

# Total item count
count = s.get(f"{URL}/api/resource/Item", params={"limit": 1}, timeout=15)
print(f"\nTotal items visible in first page (checking count)...")
r3 = s.get(f"{URL}/api/method/frappe.client.get_count",
           params={"doctype": "Item", "filters": "[]"}, timeout=15)
print("Count:", r3.json().get("message"))
