import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Get all users except Guest
r = s.get(f"{URL}/api/resource/User",
          params={"fields": '["name","user_type","enabled"]',
                  "limit": 200,
                  "filters": '[["name","!=","Guest"]]'},
          timeout=15)
users = r.json().get("data", [])
print(f"Total users: {len(users)}")

ok = skip = fail = 0
for u in users:
    if u["user_type"] == "System User":
        print(f"  skip  : {u['name']} (already System User)")
        skip += 1
        continue
    r2 = s.put(f"{URL}/api/resource/User/{requests.utils.quote(u['name'])}",
               json={"user_type": "System User"}, timeout=15)
    if r2.status_code in (200, 201):
        print(f"  updated: {u['name']}  {u['user_type']} -> System User")
        ok += 1
    else:
        print(f"  ERROR  : {u['name']} {r2.status_code} {r2.text[:120]}")
        fail += 1

print(f"\nDone: {ok} updated, {skip} already system users, {fail} failed")
