import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1},
          timeout=60)
msg = r.json().get("message", {})
print("Columns:")
for c in msg.get("columns", []):
    print(f"  {c}")
print("\nFirst 3 rows:")
for row in msg.get("result", [])[:3]:
    if isinstance(row, dict):
        print(f"  {row}")
