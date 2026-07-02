import os
import requests, json
requests.packages.urllib3.disable_warnings()

URL  = "https://www.karavanimports.com"
PASS = os.environ.get("ERP_ADMIN_PWD")

CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI  = f"{URL}/api/method/frappe.integrations.connected_app.callback"

s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr":"Administrator","pwd":PASS}, timeout=15)

# ── 1. Create / update Connected App ─────────────────────────────────────────
print("[1] Connected App...")
app_name = "Google Mail"
chk = s.get(f"{URL}/api/resource/Connected%20App/{requests.utils.quote(app_name)}", timeout=10)

app_body = {
    "doctype": "Connected App",
    "name": app_name,
    "provider_name": "Google Mail",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "authorization_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uri": REDIRECT_URI,
    "scopes": [
        {"scope": "https://mail.google.com/"},
        {"scope": "https://www.googleapis.com/auth/gmail.send"},
    ],
}

if chk.status_code == 200:
    r = s.put(f"{URL}/api/resource/Connected%20App/{requests.utils.quote(app_name)}", json=app_body, timeout=20)
    print(f"  updated: {r.status_code}")
else:
    r = s.post(f"{URL}/api/resource/Connected%20App", json=app_body, timeout=20)
    print(f"  created: {r.status_code}")

if r.status_code not in (200, 201):
    print("  ERROR:", r.text[:300])
else:
    print("  Connected App OK:", r.json().get("data", {}).get("name"))

# ── 2. Create / update Email Account ─────────────────────────────────────────
print("\n[2] Email Account...")
ea_name = "Karavan Imports"
chk2 = s.get(f"{URL}/api/resource/Email%20Account/{requests.utils.quote(ea_name)}", timeout=10)

ea_body = {
    "doctype": "Email Account",
    "email_account_name": ea_name,
    "email_id": "accounting@karavanimports.com",
    "service": "GMail",
    "auth_method": "OAuth",
    "connected_app": r.json().get("data", {}).get("name", app_name),
    "connected_user": "Administrator",
    "enable_outgoing": 1,
    "default_outgoing": 1,
    "enable_incoming": 0,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": 1,
    "send_notification_to": "admin@atlaslakes.com",
}

if chk2.status_code == 200:
    r2 = s.put(f"{URL}/api/resource/Email%20Account/{requests.utils.quote(ea_name)}", json=ea_body, timeout=20)
    print(f"  updated: {r2.status_code}")
else:
    r2 = s.post(f"{URL}/api/resource/Email%20Account", json=ea_body, timeout=20)
    print(f"  created: {r2.status_code}")

if r2.status_code not in (200, 201):
    print("  ERROR:", r2.text[:300])
else:
    data = r2.json().get("data", {})
    print(f"  Email Account OK: {data.get('name')} | outgoing: {data.get('enable_outgoing')}")

print("\nDone. Next: open ERPNext -> Email Account -> Karavan Imports -> click Authenticate to complete OAuth flow.")
