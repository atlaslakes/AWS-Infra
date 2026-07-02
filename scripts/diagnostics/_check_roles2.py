import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

def get(path, **params):
    return s.get(f"{URL}{path}", params=params, timeout=15).json().get("data", [])

def getdoc(doctype, name):
    return s.get(f"{URL}/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(name)}", timeout=15).json().get("data", {})

# Role Profile details
for rp in ["Customer Role Profile", "Customer", "Inventory", "Accounts"]:
    doc = getdoc("Role Profile", rp)
    roles = [r["role"] for r in doc.get("roles", [])]
    print(f"\nRole Profile: {rp}")
    print(f"  Roles: {roles}")

# Workspace details for our 3 key ones
for ws in ["Inventory Manager-Administrator", "Customer Dashboard-Administrator", "Accountant-Administrator"]:
    doc = getdoc("Workspace", ws)
    print(f"\nWorkspace: {ws}")
    print(f"  roles: {[r.get('role') for r in doc.get('roles', [])]}")
    print(f"  shortcuts: {[sc.get('label') or sc.get('link_to') for sc in doc.get('shortcuts', [])]}")
    print(f"  charts: {[c.get('chart_name') for c in doc.get('charts', [])]}")
    print(f"  cards/links: {[lk.get('label') for lk in doc.get('links', [])][:10]}")

# Check what roles exist with desk_access
print("\n=== All Roles (desk_access=1) ===")
roles = get("/api/resource/Role", fields='["name","desk_access"]', limit=200,
            filters='[["desk_access","=",1]]')
for r in roles:
    print(f"  {r['name']}")
