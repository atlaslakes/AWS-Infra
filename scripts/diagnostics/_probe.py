import os
import requests, json
requests.packages.urllib3.disable_warnings()

URL  = "http://3.216.86.193"
PASS = os.environ.get("ERP_ADMIN_PWD")

s = requests.Session(); s.verify = False
r = s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=15)
print("Login:", r.status_code, r.json().get("message", r.text[:80]))

company = s.get(f"{URL}/api/resource/Company", params={"fields": '["name","abbr"]', "limit": 5}, timeout=15).json().get("data", [])
print("Companies:", company)

wh = s.get(f"{URL}/api/resource/Warehouse", params={"fields": '["name","is_group"]', "limit": 20}, timeout=15).json().get("data", [])
print("Warehouses:", wh)

items = s.get(f"{URL}/api/resource/Item", params={"fields": '["name"]', "limit": 5}, timeout=15).json().get("data", [])
print("Items (first 5):", [i["name"] for i in items])

pf = s.get(f"{URL}/api/resource/Print%20Format/Atlas%20Invoice%20Tracking%20Classic", timeout=15)
print("Print Format exists:", pf.status_code == 200)
