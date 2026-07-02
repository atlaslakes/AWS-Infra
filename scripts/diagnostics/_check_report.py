import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/resource/Report/Inventory Manager", timeout=15)
data = r.json().get("data", {})
print("report_type:", data.get("report_type"))
print("\n--- QUERY ---")
print(data.get("query","(empty)"))
print("\n--- SCRIPT ---")
print(data.get("script","(empty)")[:300])
