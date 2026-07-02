import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Check role profile 'admin'
r = s.get(f"{URL}/api/resource/Role%20Profile/admin", timeout=15)
rp = r.json().get("data", {})
print("=== admin profile roles ===")
for x in rp.get("roles", []):
    print(f"  {x['role']}")

# Check karavanimports user roles directly
r2 = s.get(f"{URL}/api/resource/User/karavanimports%40atlaslakes.com", timeout=15)
u = r2.json().get("data", {})
print(f"\n=== karavanimports user ===")
print(f"user_type: {u.get('user_type')}")
print(f"role_profile: {u.get('role_profile_name')}")
print(f"roles: {[x['role'] for x in u.get('roles', [])]}")

# Check what roles have access to Warehouse
r3 = s.get(f"{URL}/api/resource/DocPerm",
           params={"fields": '["parent","role","read","write","create","delete"]',
                   "filters": '[["parent","=","Warehouse"]]', "limit": 50}, timeout=15)
print("\n=== Warehouse permissions ===")
for p in r3.json().get("data", []):
    print(f"  {p['role']:35} read:{p['read']} write:{p['write']} create:{p['create']}")
