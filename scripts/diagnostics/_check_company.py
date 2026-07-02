import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
r = s.get(f"{URL}/api/resource/Company", params={"fields": '["name","abbr","default_currency"]', "limit": 10}, timeout=15)
for c in r.json().get("data", []):
    print(c)
