import os, requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

for status_code, label in [(0,"Draft"), (1,"Submitted"), (2,"Cancelled")]:
    r = s.get(f"{URL}/api/resource/Sales Invoice",
              params={"filters": f'[["docstatus","=",{status_code}]]',
                      "fields": '["name","customer","grand_total","posting_date"]',
                      "limit": 200}, timeout=15)
    rows = r.json().get("data", [])
    print(f"{label} ({len(rows)}):")
    for row in rows[:5]:
        print(f"  {row['name']} | {row.get('customer','?')} | ${row.get('grand_total',0)} | {row.get('posting_date','')}")
    if len(rows) > 5:
        print(f"  ... and {len(rows)-5} more")
