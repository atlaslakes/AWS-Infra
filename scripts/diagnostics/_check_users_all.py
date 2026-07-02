import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/resource/User",
          params={"fields": '["name","full_name","user_type","enabled","role_profile_name"]',
                  "limit": 200}, timeout=15)
users = r.json().get("data", [])
print(f"Total users: {len(users)}\n")
for u in users:
    print(f"  {u['name']:40} | {u.get('user_type'):15} | enabled:{u.get('enabled')} | profile:{u.get('role_profile_name')}")

# Also check Item for custom_cases_on_hand field
r2 = s.get(f"{URL}/api/resource/Item/BEAN-0001",
           params={"fields": '["name","item_name","custom_cases_on_hand","custom_items_per_case"]'},
           timeout=15)
print("\n=== Sample Item fields ===")
print(r2.json())
