import os, requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

for status_code, label in [(2,"Cancelled"), (0,"Draft")]:
    r = s.get(f"{URL}/api/resource/Sales Invoice",
              params={"filters": f'[["docstatus","=",{status_code}]]',
                      "fields": '["name"]', "limit": 500}, timeout=15)
    names = [row["name"] for row in r.json().get("data", [])]
    print(f"Deleting {len(names)} {label} invoices...")
    for name in names:
        r2 = s.delete(f"{URL}/api/resource/Sales Invoice/{name}", timeout=15)
        print(f"  {name}: {r2.status_code}")

print("Done.")
