import os
import requests

requests.packages.urllib3.disable_warnings()
PROD_URL = "https://erpnext.karavanimports.com"
PASS = os.environ.get("ERP_ADMIN_PWD")


def title_case(s):
    return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in s.split(" "))


s = requests.Session()
s.verify = False
s.post(f"{PROD_URL}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=20)
print("Logged in")

r = s.get(f"{PROD_URL}/api/resource/Item",
          params={"limit_page_length": 0, "fields": '["name","item_name"]'}, timeout=30)
items = r.json().get("data", [])
print(f"{len(items)} items total")

ok = fail = skipped = 0
for it in items:
    old_name = it.get("item_name") or ""
    new_name = title_case(old_name)
    if new_name == old_name:
        skipped += 1
        continue
    r = s.put(f"{PROD_URL}/api/resource/Item/{it['name']}",
               json={"item_name": new_name}, timeout=30)
    if r.status_code == 200:
        print(f"  {it['name']:14} {old_name!r} -> {new_name!r}")
        ok += 1
    else:
        print(f"  ERR {it['name']}: {r.status_code} {r.text[:120]}")
        fail += 1

print(f"\nUpdated: {ok} OK, {fail} failed, {skipped} already correct")
