import os
"""
Sets up ERPNext for Stripe payments (cards + ACH via Stripe):

  1. Custom fields on Customer / Supplier to store Stripe identifiers
  2. Custom fields on Sales Invoice / Purchase Invoice to drive payments
  3. "ACH" and "Card" Modes of Payment, so Payment Entries created by the
     payments backend are distinguishable from manually entered ones
  4. A restricted "Payments Integration" API user, so the Lambda backend
     does not need the admin-level ERPNEXT_API_KEY (NOTE: the deployed
     stack is currently still using the broad admin API key as a stopgap —
     this is a pre-existing gap, not introduced by the Stripe migration)

This is a schema migration only. It does NOT migrate the old custom_dwolla_*/
custom_plaid_item_id values on any existing party record (e.g. the
`customertest` sandbox record from earlier ACH testing) — those are stale
sandbox data with zero production relevance and are simply left in place;
the new backend never reads those field names again.

Run once against the site:
    ERPNEXT_API_KEY=... ERPNEXT_API_SECRET=... python setup_stripe_payments.py
"""

import requests, json, sys
requests.packages.urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
API_KEY = os.environ.get("ERPNEXT_API_KEY")
API_SECRET = os.environ.get("ERPNEXT_API_SECRET")

s = requests.Session(); s.verify = False
if API_KEY and API_SECRET:
    s.headers["Authorization"] = f"token {API_KEY}:{API_SECRET}"
    print("Using API key auth\n")
else:
    login_resp = s.post(f"{URL}/api/method/login", data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"), "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
    if login_resp.status_code != 200:
        print(f"Login failed {login_resp.status_code}: {login_resp.text[:300]}")
        sys.exit(1)
    print("Using password auth\n")

def q(n): return requests.utils.quote(str(n), safe="")

def exists(dt, name):
    return s.get(f"{URL}/api/resource/{q(dt)}/{q(name)}", timeout=10).status_code == 200

def create(dt, doc):
    r = s.post(f"{URL}/api/resource/{q(dt)}", json=doc, timeout=20)
    if r.status_code in (200, 201): return r.json()["data"]
    raise RuntimeError(f"CREATE {dt} failed {r.status_code}: {r.text[:300]}")

def update(dt, name, doc):
    r = s.put(f"{URL}/api/resource/{q(dt)}/{q(name)}", json=doc, timeout=20)
    if r.status_code in (200, 201): return r.json()["data"]
    raise RuntimeError(f"UPDATE {dt}/{name} failed {r.status_code}: {r.text[:300]}")

def upsert(dt, name, doc):
    if exists(dt, name):
        d = update(dt, name, doc)
        print(f"  updated : {dt} / {name}")
        return d
    else:
        d = create(dt, doc)
        print(f"  created : {dt} / {name}")
        return d


# ── 1. Custom fields on Customer / Supplier ───────────────────────────────────
print("=== [1] Custom Fields: Customer / Supplier ===")

for dt in ("Customer", "Supplier"):
    upsert("Custom Field", f"{dt}-custom_stripe_customer_id", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Stripe Customer ID",
        "fieldname": "custom_stripe_customer_id",
        "fieldtype": "Data",
        "read_only": 1,
        "description": "Stripe Customer resource this party is linked to.",
    })
    upsert("Custom Field", f"{dt}-custom_stripe_payment_method_id", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Stripe Payment Method ID",
        "fieldname": "custom_stripe_payment_method_id",
        "fieldtype": "Data",
        "read_only": 1,
        "insert_after": "custom_stripe_customer_id",
        "description": "Saved card or bank account (Stripe PaymentMethod) attached to this party.",
    })
    upsert("Custom Field", f"{dt}-custom_payment_method_type", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Payment Method Type",
        "fieldname": "custom_payment_method_type",
        "fieldtype": "Select",
        "options": "\nCard\nBank",
        "read_only": 1,
        "insert_after": "custom_stripe_payment_method_id",
        "description": "Type of the saved Stripe payment method.",
    })
    upsert("Custom Field", f"{dt}-custom_bank_linked", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Bank Linked",
        "fieldname": "custom_bank_linked",
        "fieldtype": "Check",
        "read_only": 1,
        "insert_after": "custom_payment_method_type",
        "description": "Set by the payments backend once a bank PaymentMethod is attached with an active mandate.",
    })
    upsert("Custom Field", f"{dt}-custom_card_on_file", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Card On File",
        "fieldname": "custom_card_on_file",
        "fieldtype": "Check",
        "read_only": 1,
        "insert_after": "custom_bank_linked",
        "description": "Set by the payments backend once a card PaymentMethod is attached.",
    })
    upsert("Custom Field", f"{dt}-custom_stripe_mandate_id", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Stripe Mandate ID",
        "fieldname": "custom_stripe_mandate_id",
        "fieldtype": "Data",
        "read_only": 1,
        "insert_after": "custom_card_on_file",
        "description": "ACH Direct Debit mandate backing the saved bank PaymentMethod, if any.",
    })


# ── 1b. ACH authorization (NACHA) — Customer only ─────────────────────────────
# NACHA requires a retained authorization before debiting a consumer/business
# bank account. This is federal regulation, not a Stripe- or Dwolla-specific
# policy, so it survives the migration unchanged. Base44 (or attach-payment-method,
# when it captures a Stripe mandate) must write these. autopay-scan refuses to
# initiate a "collect" charge for a customer without custom_ach_authorization_date set.
print("\n=== [1b] Custom Fields: Customer ACH authorization ===")

_AUTH_FIELDS = [
    ("custom_ach_authorization_date", "ACH Authorization Date", "Datetime",
     "When the customer authorized recurring ACH debits (NACHA record)."),
    ("custom_ach_authorization_ip", "ACH Authorization IP", "Data",
     "IP address the authorization was captured from."),
    ("custom_ach_authorization_text", "ACH Authorization Text", "Small Text",
     "Exact consent language shown to and accepted by the customer."),
    ("custom_ach_authorization_reference", "ACH Authorization Reference", "Data",
     "Base44 consent-record id for this authorization."),
]
_prev = "custom_stripe_mandate_id"
for fname, label, ftype, desc in _AUTH_FIELDS:
    upsert("Custom Field", f"Customer-{fname}", {
        "doctype": "Custom Field", "dt": "Customer",
        "label": label, "fieldname": fname, "fieldtype": ftype,
        "read_only": 1, "insert_after": _prev, "description": desc,
    })
    _prev = fname


# ── 2. Custom fields on Sales Invoice / Purchase Invoice ──────────────────────
print("\n=== [2] Custom Fields: Sales Invoice / Purchase Invoice ===")

for dt in ("Sales Invoice", "Purchase Invoice"):
    upsert("Custom Field", f"{dt}-custom_autopay_enabled", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Auto-Pay via Stripe",
        "fieldname": "custom_autopay_enabled",
        "fieldtype": "Check",
        "bold": 1,
        "in_list_view": 1,
        "allow_on_submit": 1,
        "description": "When checked, the autopay-scan Lambda will initiate an off-session Stripe charge once due.",
    })
    upsert("Custom Field", f"{dt}-custom_stripe_payment_intent_id", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Stripe Payment Intent ID",
        "fieldname": "custom_stripe_payment_intent_id",
        "fieldtype": "Data",
        "read_only": 1,
        "allow_on_submit": 1,
        "insert_after": "custom_autopay_enabled",
        "description": "Stripe PaymentIntent resource ID for the initiated payment.",
    })
    upsert("Custom Field", f"{dt}-custom_payment_status", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Payment Status",
        "fieldname": "custom_payment_status",
        "fieldtype": "Select",
        "options": "\nPending\nProcessing\nCompleted\nFailed\nReturned",
        "read_only": 1,
        "allow_on_submit": 1,
        "in_list_view": 1,
        "insert_after": "custom_stripe_payment_intent_id",
        "description": "Reconciled from Stripe webhook events.",
    })


# ── 2b. Child doctype: Autopay Installment + Table field ──────────────────────
print("\n=== [2b] Autopay Installment (installment plans) ===")

upsert("DocType", "Autopay Installment", {
    "doctype": "DocType",
    "name": "Autopay Installment",
    "module": "Accounts",
    "custom": 1,
    "istable": 1,
    "editable_grid": 1,
    "fields": [
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency", "reqd": 1, "in_list_view": 1},
        {"fieldname": "scheduled_date", "label": "Scheduled Date", "fieldtype": "Date", "reqd": 1, "in_list_view": 1},
        {"fieldname": "status", "label": "Status", "fieldtype": "Select",
         "options": "Pending\nProcessing\nCompleted\nFailed\nReturned", "default": "Pending", "in_list_view": 1},
        {"fieldname": "stripe_payment_intent_id", "label": "Stripe Payment Intent ID", "fieldtype": "Data", "read_only": 1},
    ],
    "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
})

for dt in ("Sales Invoice", "Purchase Invoice"):
    upsert("Custom Field", f"{dt}-custom_ach_installments", {
        "doctype": "Custom Field",
        "dt": dt,
        "label": "Autopay Installments",
        "fieldname": "custom_ach_installments",
        "fieldtype": "Table",
        "options": "Autopay Installment",
        "allow_on_submit": 1,
        "insert_after": "custom_payment_status",
        "description": "Optional payment schedule: split this invoice's total into multiple charges on different dates. Leave empty for a single full-amount auto-pay on due_date.",
    })


# ── 2c. Validation: installment amounts must sum to the invoice total ─────────
print("\n=== [2c] Server Scripts: installment sum validation ===")

validation_script = """
rows = doc.get("custom_ach_installments") or []
if rows:
    total = sum(flt(row.amount) for row in rows)
    if abs(total - flt(doc.grand_total)) > 0.01:
        frappe.throw(f"Autopay Installments must sum to the invoice total ({doc.grand_total}), got {total}.")
"""

for dt in ("Sales Invoice", "Purchase Invoice"):
    upsert("Server Script", f"ACH Installments Validation - {dt}", {
        "doctype": "Server Script",
        "name": f"ACH Installments Validation - {dt}",
        "script_type": "DocType Event",
        "reference_doctype": dt,
        "doctype_event": "Before Save",
        "enabled": 1,
        "script": validation_script,
    })


# ── 3. Modes of Payment: ACH + Card ────────────────────────────────────────────
print("\n=== [3] Modes of Payment: ACH / Card ===")

upsert("Mode of Payment", "ACH", {
    "doctype": "Mode of Payment",
    "mode_of_payment": "ACH",
    "enabled": 1,
    "type": "Bank",
})

upsert("Mode of Payment", "Card", {
    "doctype": "Mode of Payment",
    "mode_of_payment": "Card",
    "enabled": 1,
    "type": "Bank",
})


# ── 4. Restricted API user for the payments backend ───────────────────────────
print("\n=== [4] Payments Integration user ===")

PAYMENTS_USER = "payments-integration@karavanimports.com"

if exists("User", PAYMENTS_USER):
    print(f"  exists  : User / {PAYMENTS_USER}")
else:
    create("User", {
        "doctype": "User",
        "email": PAYMENTS_USER,
        "first_name": "Payments",
        "last_name": "Integration",
        "send_welcome_email": 0,
        "user_type": "System User",
        "roles": [
            {"doctype": "Has Role", "role": "Accounts User"},
        ],
    })
    print(f"  created : User / {PAYMENTS_USER}")

print("""
=== Done ===

Custom fields created on Customer / Supplier:
  custom_stripe_customer_id, custom_stripe_payment_method_id, custom_payment_method_type,
  custom_bank_linked, custom_card_on_file, custom_stripe_mandate_id

Custom fields created on Sales Invoice / Purchase Invoice:
  custom_autopay_enabled, custom_stripe_payment_intent_id, custom_payment_status, custom_ach_installments

"Autopay Installment" child doctype created (optional per-invoice payment schedule).
Server Scripts created validating installment amounts sum to the invoice total.

Modes of Payment "ACH" and "Card" created.

Payments Integration user created: payments-integration@karavanimports.com
  -> Generate an API key/secret for this user in ERPNext
     (User -> API Access -> Generate Keys) and store them in the
     payments-backend Secrets Manager secret as the ERPNext credentials
     the Lambda backend authenticates with (do NOT reuse the admin key —
     the deployed stack is currently still using it as a pre-existing
     stopgap, unrelated to this migration).

NOTE: this is a schema migration only. Old custom_dwolla_*/custom_plaid_item_id
values on any existing sandbox party record (e.g. `customertest`) are left
untouched — the new backend never reads those field names.
""")
