import os
import requests, json
requests.packages.urllib3.disable_warnings()

URL  = "https://www.karavanimports.com"
PASS = os.environ.get("ERP_ADMIN_PWD")

s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr":"Administrator","pwd":PASS}, timeout=15)

# Find which Connected App is linked to the Email Account
ea = s.get(f"{URL}/api/resource/Email%20Account/Karavan%20Imports", timeout=15).json().get('data', {})
linked_app = ea.get('connected_app')
print(f"Email Account linked to Connected App: {linked_app}")

# Delete the duplicate
all_apps = s.get(f"{URL}/api/resource/Connected%20App",
                 params={"fields": '["name"]', "limit": 20}, timeout=15).json().get('data', [])
for app in all_apps:
    if app['name'] != linked_app:
        r = s.delete(f"{URL}/api/resource/Connected%20App/{app['name']}", timeout=10)
        print(f"Deleted duplicate {app['name']}: {r.status_code}")

# Fix the redirect URI on the linked app to use HTTPS domain
correct_redirect = f"{URL}/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/{linked_app}"
print(f"\nSetting redirect URI to:\n  {correct_redirect}")

r = s.put(f"{URL}/api/resource/Connected%20App/{linked_app}",
          json={"redirect_uri": correct_redirect}, timeout=15)
print(f"Update: {r.status_code}")

# Verify
updated = s.get(f"{URL}/api/resource/Connected%20App/{linked_app}", timeout=15).json().get('data', {})
print(f"Confirmed redirect_uri: {updated.get('redirect_uri')}")

print(f"""
ACTION REQUIRED — add this exact URI to Google Cloud Console:
  {correct_redirect}

Steps:
  1. Go to console.cloud.google.com -> KaravanImportsERPnext project
  2. APIs & Services -> Credentials -> click your OAuth 2.0 Client
  3. Under Authorized redirect URIs -> Add URI -> paste the URI above
  4. Save
""")
