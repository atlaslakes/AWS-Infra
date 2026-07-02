import os
"""
Diagnose and fix the Gmail OAuth email setup in ERPNext.

Root cause: troubleshooting changed connected_user to karavanimports@atlaslakes.com,
which has no OAuth token, so ERPNext can't send mail. Also verifies the redirect URI
is in the correct Frappe v15 format.

Keeps original email addresses:
  - Sending from : accounting@karavanimports.com
  - Notify to    : admin@atlaslakes.com
  - Connected App: Google Mail
  - OAuth creds  : the original Google Cloud client

After running this script you must re-authenticate once:
  ERPNext -> Email Account -> Karavan Imports -> click "Authenticate"
"""

import requests, json, sys

requests.packages.urllib3.disable_warnings()
URL  = "https://www.karavanimports.com"
PASS = os.environ.get("ERP_ADMIN_PWD")

CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

s = requests.Session(); s.verify = False
r = s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=15)
if r.status_code != 200:
    sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")
print("Logged in as Administrator\n")


def get(path, **params):
    return s.get(f"{URL}{path}", params=params, timeout=15)

def put(path, body):
    return s.put(f"{URL}{path}", json=body, timeout=20)

def post(path, body):
    return s.post(f"{URL}{path}", json=body, timeout=20)

def q(name):
    return requests.utils.quote(str(name), safe="")


# ── 1. Find which Connected App is linked to the Email Account ────────────────
print("=== [1] Email Account — current state ===")
ea_r = get(f"/api/resource/Email%20Account/Karavan%20Imports")
if ea_r.status_code != 200:
    print("  Email Account 'Karavan Imports' not found — will create it later")
    ea_data = {}
    linked_app = None
else:
    ea_data = ea_r.json().get("data", {})
    linked_app = ea_data.get("connected_app")
    print(f"  connected_app   : {linked_app}")
    print(f"  connected_user  : {ea_data.get('connected_user')}")
    print(f"  email_id        : {ea_data.get('email_id')}")
    print(f"  enable_outgoing : {ea_data.get('enable_outgoing')}")


# ── 2. Find all Connected Apps and pick the right one ─────────────────────────
print("\n=== [2] Connected Apps ===")
apps_r = get("/api/resource/Connected%20App",
             fields='["name","provider_name","client_id","redirect_uri"]', limit=20)
apps = apps_r.json().get("data", [])
for a in apps:
    print(f"  {a['name']} | {a.get('provider_name')} | redirect: {a.get('redirect_uri','')[:80]}")

# Prefer the app already linked; fall back to any Google Mail app
target_app = linked_app
if not target_app:
    for a in apps:
        if "google" in (a.get("provider_name") or "").lower():
            target_app = a["name"]
            break
if not target_app and apps:
    target_app = apps[0]["name"]

if not target_app:
    print("  No Connected App found — will create one")


# ── 3. Correct redirect URI (Frappe v15 format) ───────────────────────────────
# Frappe v15 uses: /api/method/frappe.integrations.doctype.connected_app.connected_app.callback/<app-name>
# The old format (/api/method/frappe.integrations.connected_app.callback) does NOT work in v15.

if target_app:
    correct_redirect = (
        f"{URL}/api/method/frappe.integrations.doctype."
        f"connected_app.connected_app.callback/{target_app}"
    )
else:
    correct_redirect = (
        f"{URL}/api/method/frappe.integrations.doctype."
        f"connected_app.connected_app.callback/Google-Mail"
    )

print(f"\n=== [3] Setting correct redirect URI ===")
print(f"  {correct_redirect}")

app_body = {
    "doctype": "Connected App",
    "provider_name": "Google Mail",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "authorization_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uri": correct_redirect,
    "scopes": [
        {"scope": "https://mail.google.com/"},
        {"scope": "https://www.googleapis.com/auth/gmail.send"},
    ],
}

if target_app:
    r3 = put(f"/api/resource/Connected%20App/{q(target_app)}", app_body)
    print(f"  Updated Connected App '{target_app}': {r3.status_code}")
    if r3.status_code not in (200, 201):
        print(f"  ERROR: {r3.text[:300]}")
    else:
        target_app = r3.json().get("data", {}).get("name", target_app)
else:
    app_body["name"] = "Google Mail"
    r3 = post("/api/resource/Connected%20App", app_body)
    print(f"  Created Connected App: {r3.status_code}")
    if r3.status_code in (200, 201):
        target_app = r3.json().get("data", {}).get("name", "Google Mail")
    else:
        print(f"  ERROR: {r3.text[:300]}")
        sys.exit(1)


# ── 4. Fix Email Account — restore connected_user to Administrator ─────────────
# IMPORTANT: connected_user must match the ERPNext user who will authenticate
# with Google. Changing it to any other user breaks the stored OAuth token lookup.
print(f"\n=== [4] Fixing Email Account ===")
ea_body = {
    "doctype": "Email Account",
    "email_account_name": "Karavan Imports",
    "email_id": "accounting@karavanimports.com",
    "service": "GMail",
    "auth_method": "OAuth",
    "connected_app": target_app,
    "connected_user": "Administrator",   # must match who clicks Authenticate in UI
    "enable_outgoing": 1,
    "default_outgoing": 1,
    "enable_incoming": 0,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": 1,
    "send_notification_to": "admin@atlaslakes.com",
}

if ea_data:
    r4 = put(f"/api/resource/Email%20Account/{q('Karavan Imports')}", ea_body)
    print(f"  Updated: {r4.status_code}")
    if r4.status_code not in (200, 201):
        print(f"  ERROR: {r4.text[:300]}")
    else:
        d = r4.json().get("data", {})
        print(f"  connected_app  : {d.get('connected_app')}")
        print(f"  connected_user : {d.get('connected_user')}")
        print(f"  email_id       : {d.get('email_id')}")
else:
    r4 = post("/api/resource/Email%20Account", ea_body)
    print(f"  Created: {r4.status_code}")
    if r4.status_code not in (200, 201):
        print(f"  ERROR: {r4.text[:300]}")


# ── 5. Summary ────────────────────────────────────────────────────────────────
print(f"""
=== Done ===

Connected App : {target_app}
Redirect URI  : {correct_redirect}
Email Account : Karavan Imports
  Sending from  : accounting@karavanimports.com
  Notify to     : admin@atlaslakes.com
  connected_user: Administrator

REQUIRED — add this URI to Google Cloud Console (if not already there):
  {correct_redirect}

  Steps:
    1. console.cloud.google.com -> KaravanImportsERPnext project
    2. APIs & Services -> Credentials -> your OAuth 2.0 Client ID
    3. Authorized redirect URIs -> Add URI -> paste above
    4. Save

REQUIRED — re-authenticate OAuth in ERPNext:
  1. Go to https://www.karavanimports.com/app/email-account/Karavan Imports
  2. Click "Authenticate" (top-right of the form)
  3. Sign in with accounting@karavanimports.com in the Google popup
  4. Grant mail permissions
  5. Save the Email Account

After those two steps email should work again.
""")
