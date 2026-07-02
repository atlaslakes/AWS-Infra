import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/resource/Item Group",
          params={"fields": '["name","parent_item_group"]', "limit": 100}, timeout=15)
for g in r.json().get("data", []):
    print(f"  {g['name']:40} parent={g['parent_item_group']}")
