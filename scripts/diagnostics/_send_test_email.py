import os, requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Check existing email accounts
r = s.get(f"{URL}/api/resource/Email Account",
          params={"fields": '["name","email_id","default_outgoing","enable_outgoing","service"]'},
          timeout=15)
accounts = r.json().get("data", [])
print("Email accounts configured:")
for a in accounts:
    print(f"  {a['name']} | {a['email_id']} | outgoing={a['enable_outgoing']} | default={a['default_outgoing']}")
