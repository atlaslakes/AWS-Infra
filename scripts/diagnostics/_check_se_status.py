import os, requests, time
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

se_name = "MAT-STE-2026-00010"
for i in range(6):
    r = s.get(f"{URL}/api/resource/Stock Entry/{se_name}", timeout=15)
    data = r.json().get("data", {})
    print(f"[{i}] docstatus={data.get('docstatus')}  (0=draft,1=submitted,2=cancelled)")
    if data.get("docstatus") == 1:
        break
    time.sleep(5)

r2 = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
           params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows2 = [row for row in r2.json().get("message", {}).get("result", []) if isinstance(row, dict)]
after_row = next((x for x in rows2 if x.get("item_id") == "BEAN-0001"), None)
print("Cases On Hand now:", after_row.get("cases_on_hand") if after_row else None)
