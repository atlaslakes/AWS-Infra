import os, requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Delete the manual deduction server scripts — no longer needed with native stock
for name in ["Deduct Cases On Hand on Invoice Submit", "Restore Cases On Hand on Invoice Cancel"]:
    r = s.delete(f"{URL}/api/resource/Server Script/{name}", timeout=15)
    print(f"Deleted '{name}': {r.status_code}" if r.status_code in (200, 202) else f"Not found or failed '{name}': {r.status_code}")
