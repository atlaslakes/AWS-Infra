import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Get the Inventory Manager workspace
r = s.get(f"{URL}/api/resource/Workspace/Inventory Manager-Administrator", timeout=15)
ws = r.json().get("data", {})
print("=== Workspace fields ===")
for k in ["name", "label", "module", "is_hidden"]:
    print(f"  {k}: {ws.get(k)}")

print("\n=== Links ===")
for l in ws.get("links", []):
    print(f"  [{l.get('type')}] {l.get('label')} -> {l.get('link_to')}")

print("\n=== Shortcuts ===")
for sc in ws.get("shortcuts", []):
    print(f"  {sc.get('label')} -> {sc.get('link_to')} ({sc.get('type')})")

# Check what item_groups exist
print("\n=== Item Groups ===")
ig = s.get(f"{URL}/api/resource/Item Group", params={"fields": '["name","parent_item_group"]', "limit": 50}, timeout=15)
for g in ig.json().get("data", []):
    print(f"  {g['name']} (parent: {g.get('parent_item_group')})")

# Check if any Web Forms exist
wf = s.get(f"{URL}/api/resource/Web Form", params={"fields": '["name","doc_type","title"]', "limit": 20}, timeout=15)
print("\n=== Existing Web Forms ===")
for w in wf.json().get("data", []):
    print(f"  {w['name']} -> {w.get('doc_type')}")
