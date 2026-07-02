import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Check if web form shows up as a Page
print("=== Pages ===")
r = s.get(f"{URL}/api/resource/Page", params={"fields": '["name","title","module"]', "limit": 50}, timeout=15)
for p in r.json().get("data", []):
    if "item" in p["name"].lower() or "inventory" in p["name"].lower() or "add" in p["name"].lower():
        print(f"  {p['name']} | {p.get('title')} | {p.get('module')}")

# Try type Page with "add-inventory-item"
print("\n=== Testing type=Page ===")
r2 = s.get(f"{URL}/api/resource/Workspace/Inventory Manager-Administrator", timeout=15)
ws = r2.json().get("data", {})
current_shortcuts = ws.get("shortcuts", [])

test_sc = {
    "doctype": "Workspace Shortcut",
    "label": "Add Item",
    "link_to": "add-inventory-item",
    "type": "Page",
    "color": "#27ae60"
}
r3 = s.put(f"{URL}/api/resource/Workspace/Inventory Manager-Administrator",
           json={"shortcuts": [test_sc] + current_shortcuts}, timeout=20)
print(f"Page type PUT: {r3.status_code}")
if r3.status_code not in (200, 201):
    d = r3.json()
    print("Error:", d.get("exception","")[:200])
    print("Msg:", str(d.get("_server_messages",""))[:200])
else:
    print("SUCCESS!")

# Try type DocType with a "new-item" link (the /new-item ERPNext route)
print("\n=== Testing create-item-from-doctype ===")
r4 = s.put(f"{URL}/api/resource/Workspace/Inventory Manager-Administrator",
           json={"shortcuts": current_shortcuts}, timeout=20)
print(f"Restore original: {r4.status_code}")

# Check what valid Page records exist for add-item
print("\n=== All pages ===")
r5 = s.get(f"{URL}/api/resource/Page", params={"fields": '["name","title"]', "limit": 100}, timeout=15)
for p in r5.json().get("data", []):
    print(f"  {p['name']}")
