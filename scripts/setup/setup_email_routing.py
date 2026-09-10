import os
"""
Purpose-specific email routing for Karavan Imports ERPNext.

Three sender identities, all authenticating through the EXISTING Google OAuth
connection (Connected App "Google Mail", connected_user "Administrator" -- the
underlying Google identity is adminuser@atlaslakes.com):

  support@karavanimports.com   incoming + outgoing   customer support -> Issue tickets
  invoices@karavanimports.com  outgoing only         Sales Invoice PDF to customer on Submit
  accounts@karavanimports.com  outgoing (default)    new-customer onboarding / credentials

karavanimports.com is a secondary domain of the atlaslakes.com Google Workspace.
The three addresses are Google Groups; adminuser@atlaslakes.com is a member of each.
Every account sets always_use_account_email_id_as_sender=1 (forces From) and
add_reply_to_header=0 (emits no Reply-To header), so neither From nor Reply-To can
fall back to adminuser@atlaslakes.com. Clients reply straight to the From address.

-------------------------------------------------------------------------------
GOOGLE WORKSPACE PREREQUISITES  (admin.google.com -- do these BEFORE running)
-------------------------------------------------------------------------------
1. For each group (support@, invoices@, accounts@karavanimports.com):
     Groups > <group> > Group settings >
       - Enable "Members can send email as the group"  (creates the send-as alias)
   For support@ only, also under "Who can post":
       - Allow "External" / "Anyone on the web" so customers can email in.

2. Gmail of adminuser@atlaslakes.com > Settings > Accounts > "Send mail as":
     confirm support@, invoices@, accounts@karavanimports.com each appear and are
     verified. Add + verify any that are missing.

3. Gmail of adminuser@atlaslakes.com > Settings > Filters > Create:
     Matches:  to:(support@karavanimports.com)
     Action:   Apply label "ERPNext Support"   (create that label first)
   ERPNext reads ONLY that label for tickets, so invoices@/accounts@ replies and
   adminuser's own mail are never turned into Issues.

-------------------------------------------------------------------------------
AFTER RUNNING
-------------------------------------------------------------------------------
- ERPNext > Email Account > (each of the 3) : should show "Awaiting Password / Token" = No
  because they reuse the Administrator OAuth token. If one still prompts, open it
  and click "Authenticate" once, signing in as adminuser@atlaslakes.com.
- Send a test from ERPNext > Email Account > Invoices > ... and confirm From shows
  invoices@karavanimports.com and there is NO Reply-To header at all.
- This script is idempotent: if the accounts already exist it updates them in
  place, so just re-run it to apply changes.

Env: ERP_ADMIN_PWD
"""

import requests, sys
requests.packages.urllib3.disable_warnings()

URL  = "https://erpnext.karavanimports.com"
PASS = os.environ.get("ERP_ADMIN_PWD")
if not PASS:
    sys.exit("Set ERP_ADMIN_PWD")

LOGIN_ID       = "adminuser@atlaslakes.com"   # real mailbox the OAuth token belongs to
CONNECTED_USER = "Administrator"
SUPPORT_LABEL  = "ERPNext Support"            # Gmail label from prerequisite step 3
INVOICE_PRINT_FORMAT = "Atlas Invoice Tracking Classic"

s = requests.Session(); s.verify = False
r = s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=15)
if r.status_code != 200:
    sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")
print("Logged in as Administrator\n")


def q(n):
    return requests.utils.quote(str(n), safe="")

def get(dt, name):
    r = s.get(f"{URL}/api/resource/{q(dt)}/{q(name)}", timeout=15)
    return r.json().get("data") if r.status_code == 200 else None

def upsert(dt, name, doc):
    if get(dt, name) is not None:
        r = s.put(f"{URL}/api/resource/{q(dt)}/{q(name)}", json=doc, timeout=25)
        label = "updated"
    else:
        r = s.post(f"{URL}/api/resource/{q(dt)}", json=doc, timeout=25)
        label = "created"
    if r.status_code in (200, 201):
        print(f"  {label:8s} {dt} / {name}")
        return r.json()["data"]
    raise RuntimeError(f"{dt} '{name}' {label} failed {r.status_code}: {r.text[:400]}")


# ---------------------------------------------------------------------------
# 0. Discover the Connected App the current account uses
# ---------------------------------------------------------------------------
print("=== [0] Existing outgoing account ===")
existing = get("Email Account", "Karavan Imports")
if existing:
    CONNECTED_APP = existing.get("connected_app") or "Google Mail"
    print(f"  Karavan Imports -> connected_app={CONNECTED_APP} "
          f"email_id={existing.get('email_id')} default_outgoing={existing.get('default_outgoing')}")
else:
    CONNECTED_APP = "Google Mail"
    print("  'Karavan Imports' not found; assuming Connected App 'Google Mail'")


# ---------------------------------------------------------------------------
# 1. Retire the old catch-all account so nothing sends as adminuser@ anymore
# ---------------------------------------------------------------------------
if existing:
    print("\n=== [1] Disable old 'Karavan Imports' account ===")
    upsert("Email Account", "Karavan Imports", {
        "doctype": "Email Account",
        "default_outgoing": 0,
        "default_incoming": 0,
        "enable_outgoing": 0,
        "enable_incoming": 0,
    })


# ---------------------------------------------------------------------------
# 2. Three purpose-specific accounts
# ---------------------------------------------------------------------------
COMMON = {
    "doctype": "Email Account",
    "service": "GMail",
    "auth_method": "OAuth",
    "connected_app": CONNECTED_APP,
    "connected_user": CONNECTED_USER,
    "login_id_is_different": 1,
    "login_id": LOGIN_ID,
    "always_use_account_email_id_as_sender": 1,   # force From = this address
    "always_use_account_name_as_sender_name": 0,  # keep the sender name the Notification sets
    # add_reply_to_header / reply_to_addresses only exist on newer Frappe v15.x.
    # The live site (15.112.0) ignores these keys; there Reply-To simply follows
    # the (now forced) sender, which is the desired result anyway. Harmless to
    # send — they take effect after a Frappe upgrade.
    "add_reply_to_header": 0,
    "reply_to_addresses": [],
    "notify_if_unreplied": 0,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": 1,
    "email_server": "imap.gmail.com",
    "use_imap": 1,
}

print("\n=== [2] Purpose-specific Email Accounts ===")

# 2a. Support -- incoming tickets + outgoing replies
upsert("Email Account", "Support", {**COMMON,
    "email_account_name": "Support",
    "email_id": "support@karavanimports.com",
    "enable_outgoing": 1,
    "default_outgoing": 0,
    "enable_incoming": 1,
    "default_incoming": 1,
    "enable_automatic_linking": 1,
    "create_contact": 0,
    "append_to": "Issue",
    "imap_folder": [{
        "doctype": "IMAP Folder",
        "folder_name": SUPPORT_LABEL,
        "append_to": "Issue",
    }],
})

# 2b. Invoices -- outgoing only
upsert("Email Account", "Invoices", {**COMMON,
    "email_account_name": "Invoices",
    "email_id": "invoices@karavanimports.com",
    "enable_outgoing": 1,
    "default_outgoing": 0,
    "enable_incoming": 0,
})

# 2c. Accounts -- outgoing, becomes the system default for generic mail
#     (staff/customer password resets, workflow alerts, welcome/credential emails)
upsert("Email Account", "Accounts", {**COMMON,
    "email_account_name": "Accounts",
    "email_id": "accounts@karavanimports.com",
    "enable_outgoing": 1,
    "default_outgoing": 1,
    "enable_incoming": 0,
})


# ---------------------------------------------------------------------------
# 3. Notification: email the invoice PDF to the customer on Submit
# ---------------------------------------------------------------------------
print("\n=== [3] Notification: Invoice to Customer ===")
upsert("Notification", "Invoice to Customer", {
    "doctype": "Notification",
    "name": "Invoice to Customer",
    "subject": "Invoice {{ doc.name }} from Karavan Imports",
    "document_type": "Sales Invoice",
    "channel": "Email",
    "event": "Submit",
    "enabled": 1,
    "is_standard": 0,
    "condition": "doc.contact_email",
    "attach_print": 1,
    "print_format": INVOICE_PRINT_FORMAT,
    "sender": "Invoices",
    "recipients": [
        {"doctype": "Notification Recipient", "receiver_by_document_field": "contact_email"},
    ],
    "message": (
        "<p>Dear {{ doc.customer_name }},</p>\n"
        "<p>Please find attached invoice <b>{{ doc.name }}</b> "
        "dated {{ frappe.utils.formatdate(doc.posting_date) }} "
        "for <b>{{ doc.get_formatted('grand_total') }}</b>.</p>\n"
        "{% if doc.due_date %}<p>Payment is due by "
        "{{ frappe.utils.formatdate(doc.due_date) }}.</p>{% endif %}\n"
        "<p>Reply to this email with any questions.</p>\n"
        "<p>Karavan Imports</p>"
    ),
})


# ---------------------------------------------------------------------------
# 4. Notification: alert staff when a new customer application comes in
# ---------------------------------------------------------------------------
print("\n=== [4] Notification: New Customer Application ===")
upsert("Notification", "New Customer Application", {
    "doctype": "Notification",
    "name": "New Customer Application",
    "subject": "New customer application: {{ doc.customer_name }}",
    "document_type": "Customer",
    "channel": "Email",
    "event": "New",
    "enabled": 1,
    "is_standard": 0,
    "condition": 'doc.custom_application_status == "Pending"',
    "sender": "Accounts",
    "recipients": [
        {"doctype": "Notification Recipient", "receiver_by_role": "Sales Manager",
         "cc": "accounts@karavanimports.com"},
    ],
    "message": (
        "<p>A new customer application was submitted from the portal:</p>\n"
        "<ul>\n"
        "<li><b>Name:</b> {{ doc.customer_name }}</li>\n"
        "<li><b>Email:</b> {{ doc.custom_customer_email or '(none provided)' }}</li>\n"
        "<li><b>Status:</b> {{ doc.custom_application_status }}</li>\n"
        "</ul>\n"
        '<p><a href="{{ frappe.utils.get_url_to_form("Customer", doc.name) }}">'
        "Review in ERPNext</a></p>"
    ),
})


print(f"""
=== Done ===

Email Accounts:
  Support   support@karavanimports.com   incoming (label '{SUPPORT_LABEL}') + outgoing
  Invoices  invoices@karavanimports.com  outgoing only
  Accounts  accounts@karavanimports.com  outgoing, DEFAULT for generic system mail
  Karavan Imports .............. disabled

Notifications:
  Invoice to Customer ......... Sales Invoice on Submit, attaches '{INVOICE_PRINT_FORMAT}',
                               sent from Invoices, to doc.contact_email
  New Customer Application .... Customer on New (status Pending), sent from Accounts,
                               to role 'Sales Manager', cc accounts@karavanimports.com

Remaining manual checks:
  1. Google Workspace prerequisites at the top of this file (send-as aliases + Gmail
     filter/label) must be in place or Google will reject the group From address.
  2. ERPNext > Email Account > each new one > "Awaiting Password/Token" should be No.
     If prompted, click Authenticate once as adminuser@atlaslakes.com.
  3. Make sure each Sales Invoice has Contact Email set, or the invoice email is skipped.
""")
