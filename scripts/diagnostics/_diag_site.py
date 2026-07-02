import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False

# Login
r = s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Login:", r.status_code, r.json().get("message"))

# Check home page / desk
r2 = s.get(f"{URL}/desk", timeout=15, allow_redirects=True)
print("Desk:", r2.status_code, r2.url)

# Check email settings
r3 = s.get(f"{URL}/api/resource/Email%20Account",
           params={"fields": '["name","email_id","enable_outgoing","use_oauth","enabled"]', "limit": 10},
           timeout=15)
print("\n=== Email Accounts ===")
for e in r3.json().get("data", []):
    print(f"  {e.get('name')} | {e.get('email_id')} | outgoing:{e.get('enable_outgoing')} | oauth:{e.get('use_oauth')} | enabled:{e.get('enabled')}")

# Check server scripts
r4 = s.get(f"{URL}/api/resource/Server%20Script",
           params={"fields": '["name","disabled","script_type"]', "limit": 20}, timeout=15)
print("\n=== Server Scripts ===")
for sc in r4.json().get("data", []):
    print(f"  {sc.get('name')} | type:{sc.get('script_type')} | disabled:{sc.get('disabled')}")

# Check users
r5 = s.get(f"{URL}/api/resource/User",
           params={"fields": '["name","enabled","user_type","role_profile_name","last_login"]',
                   "filters": '[["user_type","!=","Website User"]]', "limit": 30}, timeout=15)
print("\n=== System Users ===")
for u in r5.json().get("data", []):
    print(f"  {u['name']} | enabled:{u.get('enabled')} | type:{u.get('user_type')} | profile:{u.get('role_profile_name')} | last_login:{u.get('last_login')}")

# Check workspace
r6 = s.get(f"{URL}/api/resource/Workspace",
           params={"fields": '["name","module","is_hidden"]', "limit": 30}, timeout=15)
print("\n=== Workspaces ===")
for w in r6.json().get("data", []):
    print(f"  {w.get('name')} | module:{w.get('module')} | hidden:{w.get('is_hidden')}")

# Check recent error logs
r7 = s.get(f"{URL}/api/resource/Error%20Log",
           params={"fields": '["name","method","error"]', "order_by": "creation desc", "limit": 5}, timeout=15)
print("\n=== Recent Error Logs ===")
for e in r7.json().get("data", []):
    print(f"  {e.get('name')} | {e.get('method')}")
    print(f"    {str(e.get('error',''))[:200]}")
