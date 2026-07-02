import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Check what's actually on adam
r = s.get(f"{URL}/api/resource/Customer/adam", timeout=15).json().get("data", {})
print("adam - custom_customer_email:", repr(r.get("custom_customer_email")))
print("adam - custom_application_status:", r.get("custom_application_status"))

# Set email explicitly, save, then approve in one combined PUT
print("\n--- Setting email AND approving in one save ---")
r2 = s.put(f"{URL}/api/resource/Customer/adam", json={
    "custom_customer_email": "youssef@atlaslakes.com",
    "custom_application_status": "Pending",
}, timeout=20)
print("Set pending:", r2.status_code)

r3 = s.put(f"{URL}/api/resource/Customer/adam", json={
    "custom_application_status": "Approved",
}, timeout=20)
print("Approve:", r3.status_code)
msgs = r3.json().get("_server_messages", "")
print("Server messages:", msgs[:500] if msgs else "(none)")

# Confirm email field persisted
r4 = s.get(f"{URL}/api/resource/Customer/adam", timeout=15).json().get("data", {})
print("\nadam after approve - email:", repr(r4.get("custom_customer_email")))
print("adam after approve - status:", r4.get("custom_application_status"))

# Email queue
import time; time.sleep(3)
eq = s.get(f"{URL}/api/resource/Email Queue",
           params={"fields": '["name","status","error","sender","creation"]',
                   "order_by": "creation desc", "limit": 3}, timeout=15)
print("\nEmail queue (latest 3):")
for e in eq.json().get("data", []):
    err = e.get("error", "") or ""
    print(f"  {e['name']} | {e['status']} | created:{e['creation']} | {err[:60] if err else 'ok'}")
