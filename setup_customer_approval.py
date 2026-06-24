"""
Adds customer application-approval fields to the ERPNext Customer doctype.

Fields added (in order, after customer_group):
  - Application Status section break
  - custom_application_status  (Select: Pending / Approved / Rejected)
  - custom_application_date    (Date -- when the application was received)
  - custom_approved_by         (Link to User -- who approved/rejected)
  - custom_approval_notes      (Small Text -- optional reviewer note)

These fields let warehouse staff review and approve customers submitted
through the base44 customer application form.

Usage:
  python setup_customer_approval.py
"""

import requests, json, sys

PROD_URL = "https://www.karavanimports.com"
S = requests.Session()
S.verify = False
requests.packages.urllib3.disable_warnings()

# ---- Auth -------------------------------------------------------------------
authed = False
for pwd in ("AdminAtlasLakes123!", "TempMigrate2026!"):
    r = S.post(f"{PROD_URL}/api/method/login",
               data={"usr": "Administrator", "pwd": pwd}, timeout=20)
    if r.status_code == 200:
        print(f"Logged in\n")
        authed = True
        break
if not authed:
    sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")


def _q(name):
    return requests.utils.quote(str(name), safe="")


def exists(doctype, name):
    r = S.get(f"{PROD_URL}/api/resource/{_q(doctype)}/{_q(name)}", timeout=15)
    return r.status_code == 200


def create(doctype, doc):
    r = S.post(f"{PROD_URL}/api/resource/{_q(doctype)}", json=doc, timeout=20)
    if r.status_code in (200, 201):
        return r.json()["data"]
    raise RuntimeError(f"{doctype} create failed {r.status_code}: {r.text[:400]}")


def get_or_create(doctype, name, doc):
    if exists(doctype, name):
        print(f"  exists : {doctype} / {name}")
        return
    create(doctype, doc)
    print(f"  created: {doctype} / {name}")


# ---- Custom Fields ----------------------------------------------------------
print("=== Customer Approval Fields ===")

FIELDS = [
    # Section header
    {
        "name": "Customer-custom_application_section",
        "doc": {
            "doctype": "Custom Field",
            "dt": "Customer",
            "label": "Application Approval",
            "fieldname": "custom_application_section",
            "fieldtype": "Section Break",
            "insert_after": "customer_group",
            "collapsible": 0,
        },
    },
    # Status dropdown (the key field)
    {
        "name": "Customer-custom_application_status",
        "doc": {
            "doctype": "Custom Field",
            "dt": "Customer",
            "label": "Application Status",
            "fieldname": "custom_application_status",
            "fieldtype": "Select",
            "options": "\nPending\nApproved\nRejected",
            "insert_after": "custom_application_section",
            "default": "Pending",
            "in_list_view": 1,
            "bold": 1,
            "description": "Set to Approved to allow this customer to place orders.",
        },
    },
    # Date the application was received / submitted from base44
    {
        "name": "Customer-custom_application_date",
        "doc": {
            "doctype": "Custom Field",
            "dt": "Customer",
            "label": "Application Date",
            "fieldname": "custom_application_date",
            "fieldtype": "Date",
            "insert_after": "custom_application_status",
            "description": "Date the customer application was submitted.",
        },
    },
    # Column break so date + approved-by sit side-by-side
    {
        "name": "Customer-custom_approval_col",
        "doc": {
            "doctype": "Custom Field",
            "dt": "Customer",
            "label": "",
            "fieldname": "custom_approval_col",
            "fieldtype": "Column Break",
            "insert_after": "custom_application_date",
        },
    },
    # Who approved/rejected
    {
        "name": "Customer-custom_approved_by",
        "doc": {
            "doctype": "Custom Field",
            "dt": "Customer",
            "label": "Approved / Rejected By",
            "fieldname": "custom_approved_by",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": "custom_approval_col",
            "description": "Staff member who reviewed this application.",
        },
    },
    # Free-text notes
    {
        "name": "Customer-custom_approval_notes",
        "doc": {
            "doctype": "Custom Field",
            "dt": "Customer",
            "label": "Approval Notes",
            "fieldname": "custom_approval_notes",
            "fieldtype": "Small Text",
            "insert_after": "custom_approved_by",
            "description": "Optional notes about this approval or rejection.",
        },
    },
]

for f in FIELDS:
    get_or_create("Custom Field", f["name"], f["doc"])

print("""
=== Done ===

Fields added to Customer form (below Customer Group):
  [ Application Approval section ]
    Application Status  (Pending / Approved / Rejected)  -- bold, in list view
    Application Date
    Approved / Rejected By  (User link)
    Approval Notes

To review pending applications in ERPNext:
  Selling -> Customers -> Add filter -> Application Status = Pending

To approve a customer:
  1. Open the Customer record
  2. Set Application Status = Approved
  3. Set Approved / Rejected By = your user
  4. Save
""")
