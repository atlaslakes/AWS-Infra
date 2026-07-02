import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
r = s.get(f"{URL}/api/resource/Workspace", params={"fields": '["name","label","module"]', "limit": 50}, timeout=15)
for w in r.json().get("data", []):
    print(f"{w['name']} | {w.get('label')} | {w.get('module')}")

# Also check shortcut valid types
print("\n=== Workspace Shortcut type field options ===")
df = s.get(f"{URL}/api/resource/DocField", params={
    "filters": '[["parent","=","Workspace Shortcut"],["fieldname","=","type"]]',
    "fields": '["options"]', "limit": 1
}, timeout=15)
for f in df.json().get("data", []):
    print("type options:", f.get("options"))
