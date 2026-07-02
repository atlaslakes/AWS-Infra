import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

print("=== All Users ===")
r = s.get(f"{URL}/api/resource/User",
          params={"fields": '["name","full_name","email","enabled","user_type","role_profile_name"]',
                  "limit": 200}, timeout=15)
for u in r.json().get("data", []):
    print(f"  {u['name']} | {u.get('full_name')} | enabled:{u.get('enabled')} | type:{u.get('user_type')} | profile:{u.get('role_profile_name')}")

print("\n=== All Customers ===")
r2 = s.get(f"{URL}/api/resource/Customer",
           params={"fields": '["name","customer_name","custom_application_status","custom_customer_email"]',
                   "limit": 200}, timeout=15)
for c in r2.json().get("data", []):
    print(f"  {c['name']} | {c['customer_name']} | {c.get('custom_application_status')} | email:{c.get('custom_customer_email')}")

print("\n=== Contacts ===")
r3 = s.get(f"{URL}/api/resource/Contact",
           params={"fields": '["name","full_name","email_id"]', "limit": 50}, timeout=15)
for c in r3.json().get("data", []):
    print(f"  {c['name']} | {c.get('full_name')} | {c.get('email_id')}")
