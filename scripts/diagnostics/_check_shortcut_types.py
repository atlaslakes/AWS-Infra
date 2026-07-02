import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Get Workspace Shortcut doctype definition to see all field options
r = s.get(f"{URL}/api/resource/Workspace/Inventory Manager-Administrator", timeout=15)
ws = r.json().get("data", {})
print("Current shortcuts:")
for sc in ws.get("shortcuts", []):
    print(f"  type={sc.get('type')} | {sc.get('label')} -> {sc.get('link_to')} | format={sc.get('format')}")

# Check the DocField options for Workspace Shortcut type
r2 = s.get(f"{URL}/api/resource/DocField",
           params={"filters": '[["parent","=","Workspace Shortcut"],["fieldname","=","type"]]',
                   "fields": '["fieldname","fieldtype","options"]', "limit": 5}, timeout=15)
print("\nWorkspace Shortcut 'type' field:")
for f in r2.json().get("data", []):
    print(f"  {f}")

# Try with Custom DocType field to find all option values
r3 = s.get(f"{URL}/api/method/frappe.client.get",
           params={"doctype": "DocType", "name": "Workspace Shortcut"}, timeout=15)
dt = r3.json().get("message", {})
for f in dt.get("fields", []):
    if f.get("fieldname") == "type":
        print("\nType options:", f.get("options"))
        break
