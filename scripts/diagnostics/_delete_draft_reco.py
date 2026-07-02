import os
import requests
requests.packages.urllib3.disable_warnings()
s = requests.Session(); s.verify = False
s.post("https://www.karavanimports.com/api/method/login",
       data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=20)
r = s.delete("https://www.karavanimports.com/api/resource/Stock%20Reconciliation/MAT-RECO-2026-00001", timeout=20)
print(r.status_code, r.text[:100])
