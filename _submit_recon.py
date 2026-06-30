import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

NAME = "MAT-RECO-2026-00008"

# Correct submit: PUT with docstatus=1
r = s.put(f"{URL}/api/resource/Stock%20Reconciliation/{NAME}",
          json={"docstatus": 1}, timeout=60)
print(r.status_code, r.text[:300])
