"""
Targeted fixes to the LIVE email routing on erpnext.karavanimports.com.

This is the reconcile-with-reality companion to setup_email_routing.py (which
describes an idealized clean-slate setup). The live site already has the
purpose-specific accounts, named "<Purpose> - Karavan", all sharing one Google
OAuth token (connected_user karavanimports@atlaslakes.com). What was still wrong:

  1. Notification "Auto Send Sales Invoice to Customer" had NO recipients, NO
     print format, and NO sender -> it emailed nobody, and when it did send it
     went via the default account (adminuser@atlaslakes.com).
  2. The "- Karavan" accounts didn't force their own address as sender, so mail
     through them could still surface adminuser@atlaslakes.com.

The site runs Frappe 15.112.0, which has NO add_reply_to_header /
reply_to_addresses fields on Email Account (added in a later v15.x). On this
version Reply-To just follows the resolved sender, so forcing the sender to the
account's own address (always_use_account_email_id_as_sender=1) plus routing the
Notification through an explicit sender account is the whole fix.

NOT changed here (needs a human / Google Workspace step first):
  - default_outgoing stays on "Karavan Imports" (adminuser@) — it is the only
    account proven to deliver. Move it to "Accounts - Karavan" only after
    confirming accounts@karavanimports.com is a verified "Send mail as" alias
    on karavanimports@atlaslakes.com.
  - "Support - Karavan" incoming stays off until the Gmail label/filter for
    to:(support@karavanimports.com) exists (see setup_email_routing.py header).

Idempotent. Env: ERP_ADMIN_USR / ERP_ADMIN_PWD (or ERPNEXT_API_KEY/SECRET).
"""

import os
import sys
from pathlib import Path

import requests

requests.packages.urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
INVOICE_PRINT_FORMAT = "Atlas Invoice Tracking Classic"
INVOICE_NOTIFICATION = "Auto Send Sales Invoice to Customer"
INVOICE_SENDER_ACCOUNT = "Invoices - Karavan"
INVOICE_SENDER_EMAIL = "invoice@karavanimports.com"
# "Accounting - Karavan" is deliberately excluded: it's a stale Basic-auth
# account with no stored password, so any save rejects with "Password not
# found". It plays no part in the routing plan — delete it in the UI if unused.
KARAVAN_ACCOUNTS = [
    "Invoices - Karavan",
    "Accounts - Karavan",
    "Support - Karavan",
]


def load_dotenv():
    p = Path(__file__).resolve().parents[2] / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_dotenv()
s = requests.Session()
s.verify = False
if os.environ.get("ERPNEXT_API_KEY") and os.environ.get("ERPNEXT_API_SECRET"):
    s.headers["Authorization"] = f"token {os.environ['ERPNEXT_API_KEY']}:{os.environ['ERPNEXT_API_SECRET']}"
else:
    r = s.post(f"{URL}/api/method/login",
               data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"),
                     "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=20)
    if r.status_code != 200:
        sys.exit(f"login failed {r.status_code}: {r.text[:200]}")


def q(n):
    return requests.utils.quote(str(n), safe="")


def patch(dt, name, doc):
    r = s.put(f"{URL}/api/resource/{q(dt)}/{q(name)}", json=doc, timeout=25)
    if r.status_code in (200, 201):
        print(f"  updated  {dt} / {name}")
        return r.json()["data"]
    raise RuntimeError(f"{dt} '{name}' update failed {r.status_code}: {r.text[:400]}")


print("=== [1] Notification: Auto Send Sales Invoice to Customer ===")
# sender_email must be set explicitly — on Frappe 15.112.0 a REST write of the
# `sender` link alone leaves `sender_email` NULL, and the notification's send
# path only uses the account when BOTH are set; otherwise it silently falls back
# to the default outgoing account (adminuser@atlaslakes.com).
patch("Notification", INVOICE_NOTIFICATION, {
    "doctype": "Notification",
    "is_standard": 0,
    "enabled": 1,
    "channel": "Email",
    "attach_print": 1,
    "print_format": INVOICE_PRINT_FORMAT,
    "sender": INVOICE_SENDER_ACCOUNT,
    "sender_email": INVOICE_SENDER_EMAIL,
    "condition": "doc.contact_email",
    "recipients": [
        {"doctype": "Notification Recipient", "receiver_by_document_field": "contact_email"},
    ],
})

print("\n=== [2] Force sender identity + drop Reply-To on the '- Karavan' accounts ===")
for name in KARAVAN_ACCOUNTS:
    chk = s.get(f"{URL}/api/resource/Email%20Account/{q(name)}", timeout=15)
    if chk.status_code != 200:
        print(f"  (skip) {name} not found")
        continue
    patch("Email Account", name, {
        "doctype": "Email Account",
        "always_use_account_email_id_as_sender": 1,
    })

print("""
=== Done ===

Invoice emails now: attach '%s', go to the invoice's Contact Email, and are
sent from '%s' (invoice@karavanimports.com). Verified on a live send:
  From:     Invoices Karavan <invoice@karavanimports.com>
  Reply-To: invoice@karavanimports.com
The attached PDF is rendered by the scheduler at send time (the queued row's
`attachments` carries the print-format spec).

Still manual:
  * default_outgoing is still 'Karavan Imports' (adminuser@atlaslakes.com).
  * 'Support - Karavan' incoming is still off.
""" % (INVOICE_PRINT_FORMAT, INVOICE_SENDER_ACCOUNT))
