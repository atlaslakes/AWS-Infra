"""
Reply-To sanitizer for the LIVE erpnext.karavanimports.com site.

Problem: support@karavanimports.com and accounts@karavanimports.com already
force their own address as sender (always_use_account_email_id_as_sender=1,
set by fix_live_email_routing.py), but at least one caller composes mail
with an explicit reply_to="adminuser@atlaslakes.com" kwarg passed straight
into frappe.sendmail() -- e.g. the live "[Contact Form] ..." message queued
to support@karavanimports.com. That caller isn't in this repo (not a Server
Script, not a Web Form, no custom bench app on the box -- only "erpnext" and
"frappe" are installed), so it can't be patched at the source. Frappe
15.112.0 also has no add_reply_to_header / reply_to_addresses field on Email
Account to override this at the account level (see fix_live_email_routing.py
header) and Server Script sandboxing has no `re` module and no `import`
statement available, so header rewriting has to be done with plain string
ops inside the script body.

Fix: a "DocType Event / Before Insert" Server Script on Email Queue that
inspects the raw outgoing MIME message and, whenever the resolved From
address is a real karavanimports.com brand address but the Reply-To header
still points at *@atlaslakes.com, rewrites Reply-To to match From. Internal
mail that is legitimately from an atlaslakes.com address (e.g. the old
default "Karavan Imports" / adminuser@ account) is left untouched -- it only
fires when From and the leaking Reply-To disagree.

Verified live 2026-09-11 by queuing test mail through both Support - Karavan
and Accounts - Karavan with reply_to forced to adminuser@atlaslakes.com:
both came out with Reply-To rewritten to their own karavanimports.com
address. Test rows were deleted from Email Queue afterward.

Idempotent (upsert by name). Env: ERP_ADMIN_USR / ERP_ADMIN_PWD.
"""

import os
import sys
from pathlib import Path

import requests

requests.packages.urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
SCRIPT_NAME = "Sanitize Reply-To - Email Queue"

# No `import re` / no bare `re` global in Frappe's safe_exec sandbox -- plain
# string ops only. Tabs (not spaces) because Server Script bodies must match
# Python indentation and the API stores/executes this verbatim.
SCRIPT_BODY = (
    'if doc.message and "atlaslakes.com" in doc.message:\n'
    '\tnl = "\\r\\n" if "\\r\\n" in doc.message else "\\n"\n'
    '\tlines = doc.message.split(nl)\n'
    '\tsafe_addr = None\n'
    '\tfor line in lines:\n'
    '\t\tif line.startswith("From:") and "<" in line and ">" in line:\n'
    '\t\t\tsafe_addr = line.split("<", 1)[1].split(">", 1)[0].strip()\n'
    '\t\t\tbreak\n'
    '\tif safe_addr and "atlaslakes.com" not in safe_addr.lower():\n'
    '\t\tchanged = False\n'
    '\t\tfor i, line in enumerate(lines):\n'
    '\t\t\tif line.startswith("Reply-To:") and "atlaslakes.com" in line.lower():\n'
    '\t\t\t\tlines[i] = "Reply-To: " + safe_addr\n'
    '\t\t\t\tchanged = True\n'
    '\t\tif changed:\n'
    '\t\t\tdoc.message = nl.join(lines)\n'
    '\t\t\tif doc.reply_to and "atlaslakes.com" in doc.reply_to.lower():\n'
    '\t\t\t\tdoc.reply_to = safe_addr\n'
)


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


existing = s.get(f"{URL}/api/resource/Server Script/{q(SCRIPT_NAME)}", timeout=15)
payload = {
    "doctype": "Server Script",
    "script_type": "DocType Event",
    "reference_doctype": "Email Queue",
    "doctype_event": "Before Insert",
    "disabled": 0,
    "script": SCRIPT_BODY,
}

if existing.status_code == 200:
    r = s.put(f"{URL}/api/resource/Server Script/{q(SCRIPT_NAME)}", json=payload, timeout=25)
    label = "updated"
else:
    payload["name"] = SCRIPT_NAME
    r = s.post(f"{URL}/api/resource/Server Script", json=payload, timeout=25)
    label = "created"

if r.status_code not in (200, 201):
    raise RuntimeError(f"Server Script {label} failed {r.status_code}: {r.text[:400]}")

print(f"{label} Server Script '{SCRIPT_NAME}' (DocType Event / Email Queue / Before Insert)")
print("Rewrites Reply-To to the resolved From address whenever the message's")
print("From is a karavanimports.com address but Reply-To still leaks *@atlaslakes.com.")
