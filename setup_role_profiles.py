import os
"""
Sets up 3 role profiles with dedicated workspaces and correct permissions.

Inventory Manager
  - Roles: Item Manager, Stock Manager, Stock User
  - Workspace: view/edit Items, Stock Entries, Inventory reports

Customer
  - Roles: Customer, Sales User
  - Workspace: place/edit Sales Orders, view Invoices, open Support tickets

Accountant
  - Roles: Accounts User, Accounts Manager, Sales Manager, Stock User
  - Workspace: Sales + Accounting shortcuts + 3 dashboard charts

All roles get desk_access=1 so users stay as System Users.
"""

import requests, json, sys
requests.packages.urllib3.disable_warnings()

URL  = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

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


# ── 1. Ensure all target roles have desk_access = 1 ──────────────────────────
print("=== [1] Roles — desk_access ===")
ROLES = [
    "Item Manager", "Stock Manager", "Stock User",
    "Customer", "Sales User",
    "Accounts User", "Accounts Manager", "Sales Manager",
]
for role in ROLES:
    r = s.put(f"{URL}/api/resource/Role/{q(role)}", json={"desk_access": 1}, timeout=15)
    status = "ok" if r.status_code in (200, 201) else f"ERR {r.status_code}"
    print(f"  {role}: {status}")


# ── 2. Wire Role Profiles ─────────────────────────────────────────────────────
print("\n=== [2] Role Profiles ===")

PROFILES = {
    "Inventory": ["Item Manager", "Stock Manager", "Stock User"],
    "Customer":  ["Customer", "Sales User"],
    "Accounts":  ["Accounts User", "Accounts Manager", "Sales Manager", "Stock User"],
}

for profile, roles in PROFILES.items():
    upsert("Role Profile", profile, {
        "doctype": "Role Profile",
        "role_profile": profile,
        "roles": [{"doctype": "User Role", "role": r} for r in roles],
    })


# ── 3. Dashboard Charts for Accountant ───────────────────────────────────────
print("\n=== [3] Dashboard Charts ===")

CHARTS = [
    {
        "name": "KI Monthly Sales Revenue",
        "doc": {
            "doctype": "Dashboard Chart",
            "chart_name": "KI Monthly Sales Revenue",
            "chart_type": "Group By",
            "document_type": "Sales Invoice",
            "based_on": "posting_date",
            "group_by_based_on": "posting_date",
            "group_by_type": "Sum",
            "aggregate_function_based_on": "grand_total",
            "time_interval": "Monthly",
            "timespan": "Last Year",
            "type": "Bar",
            "color": "#5e64ff",
            "is_public": 1,
            "filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
        }
    },
    {
        "name": "KI Top Selling Items",
        "doc": {
            "doctype": "Dashboard Chart",
            "chart_name": "KI Top Selling Items",
            "chart_type": "Group By",
            "document_type": "Sales Invoice Item",
            "parent_document_type": "Sales Invoice",
            "based_on": "item_name",
            "group_by_based_on": "item_name",
            "group_by_type": "Sum",
            "aggregate_function_based_on": "qty",
            "number_of_groups": 10,
            "type": "Bar",
            "color": "#00BCD4",
            "is_public": 1,
            "filters_json": "[]",
        }
    },
    {
        "name": "KI Sales by Customer",
        "doc": {
            "doctype": "Dashboard Chart",
            "chart_name": "KI Sales by Customer",
            "chart_type": "Group By",
            "document_type": "Sales Invoice",
            "based_on": "customer",
            "group_by_based_on": "customer",
            "group_by_type": "Sum",
            "aggregate_function_based_on": "grand_total",
            "number_of_groups": 10,
            "type": "Pie",
            "color": "#ff5858",
            "is_public": 1,
            "filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
        }
    },
]

for c in CHARTS:
    upsert("Dashboard Chart", c["name"], c["doc"])


# ── 4. Workspaces ─────────────────────────────────────────────────────────────
print("\n=== [4] Workspaces ===")

# helper to build shortcut rows
def sc(label, link_to, stype="DocType", color="#2490EF"):
    return {"doctype": "Workspace Shortcut", "label": label,
            "link_to": link_to, "type": stype, "color": color}

def lk(label, link_to, ltype="Link"):
    return {"doctype": "Workspace Link", "label": label,
            "link_to": link_to, "type": ltype, "hidden": 0, "onboard": 1}

def chart(chart_name):
    return {"doctype": "Workspace Chart", "chart_name": chart_name}

def role_row(role):
    return {"doctype": "Workspace Role", "role": role}


# ── 4a. Inventory Manager workspace ──────────────────────────────────────────
upsert("Workspace", "Inventory Manager-Administrator", {
    "doctype": "Workspace",
    "name": "Inventory Manager-Administrator",
    "label": "Inventory Manager",
    "module": "Stock",
    "is_hidden": 0,
    "roles": [role_row("Item Manager"), role_row("Stock Manager"), role_row("Stock User")],
    "shortcuts": [
        sc("Items",         "Item",        color="#2490EF"),
        sc("Stock Entries", "Stock Entry", color="#98a8d4"),
        sc("Item Price",    "Item Price",  color="#2ecc71"),
        sc("Warehouses",    "Warehouse",   color="#9b59b6"),
    ],
    "links": [
        {"doctype": "Workspace Link", "label": "Items",     "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Item",            "Item"),
        lk("Item Price",      "Item Price"),
        lk("Item Group",      "Item Group"),
        {"doctype": "Workspace Link", "label": "Stock",    "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Stock Entry",     "Stock Entry"),
        lk("Stock Ledger Entry", "Stock Ledger Entry"),
        lk("Warehouse",       "Warehouse"),
    ],
    "charts": [],
})


# ── 4b. Customer workspace ────────────────────────────────────────────────────
upsert("Workspace", "Customer Dashboard-Administrator", {
    "doctype": "Workspace",
    "name": "Customer Dashboard-Administrator",
    "label": "Customer Portal",
    "module": "Selling",
    "is_hidden": 0,
    "roles": [role_row("Customer"), role_row("Sales User")],
    "shortcuts": [
        sc("New Order",      "Sales Order",     color="#2490EF"),
        sc("My Orders",      "Sales Order",     color="#2ecc71"),
        sc("My Invoices",    "Sales Invoice",   color="#f39c12"),
        sc("Support",        "Issue",           color="#e74c3c"),
    ],
    "links": [
        {"doctype": "Workspace Link", "label": "Orders",   "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Sales Order",    "Sales Order"),
        {"doctype": "Workspace Link", "label": "Invoices", "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Sales Invoice",  "Sales Invoice"),
        {"doctype": "Workspace Link", "label": "Support",  "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Issue",          "Issue"),
    ],
    "charts": [],
})


# ── 4c. Accountant workspace ──────────────────────────────────────────────────
upsert("Workspace", "Accountant-Administrator", {
    "doctype": "Workspace",
    "name": "Accountant-Administrator",
    "label": "Accountant",
    "module": "Accounts",
    "is_hidden": 0,
    "roles": [role_row("Accounts User"), role_row("Accounts Manager"), role_row("Sales Manager")],
    "shortcuts": [
        sc("Sales Orders",   "Sales Order",     color="#2490EF"),
        sc("Sales Invoices", "Sales Invoice",   color="#2ecc71"),
        sc("Payments",       "Payment Entry",   color="#9b59b6"),
        sc("General Ledger", "General Ledger",  stype="Report", color="#f39c12"),
    ],
    "links": [
        {"doctype": "Workspace Link", "label": "Sales",    "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Sales Order",    "Sales Order"),
        lk("Sales Invoice",  "Sales Invoice"),
        lk("Payment Entry",  "Payment Entry"),
        {"doctype": "Workspace Link", "label": "Inventory","type": "Card Break", "link_to": "", "hidden": 0},
        lk("Item",           "Item"),
        lk("Warehouse",      "Warehouse"),
    ],
    "charts": [
        chart("KI Monthly Sales Revenue"),
        chart("KI Top Selling Items"),
        chart("KI Sales by Customer"),
    ],
})


# ── 5. Force all existing users to System User ────────────────────────────────
print("\n=== [5] All users -> System User ===")
users = s.get(f"{URL}/api/resource/User",
              params={"fields": '["name","user_type"]', "limit": 200,
                      "filters": '[["name","!=","Guest"]]'}, timeout=15).json().get("data", [])

non_sys = [u["name"] for u in users if u.get("user_type") != "System User"]
if non_sys:
    print(f"  Non-system users (need SSM bench fix): {non_sys}")
else:
    print("  All users are already System Users")


print("""
=== Done ===

Role Profiles wired:
  Inventory  -> Item Manager, Stock Manager, Stock User
  Customer   -> Customer, Sales User
  Accounts   -> Accounts User, Accounts Manager, Sales Manager, Stock User

Workspaces updated with role restrictions + shortcuts + links:
  Inventory Manager-Administrator  (Inventory profile)
  Customer Dashboard-Administrator (Customer profile)
  Accountant-Administrator         (Accounts profile)

Dashboard Charts created (Accountant workspace):
  KI Monthly Sales Revenue  (bar)
  KI Top Selling Items      (bar)
  KI Sales by Customer      (pie)

To assign a profile to a user:
  Settings -> User -> select user -> Role Profile field
""")
