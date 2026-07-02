import os
"""
Migrates ALL ERPNext customizations from POC to production.
Skips all business data (items, customers, orders, stock, etc.)

Covers:
  - Custom Fields, Property Setters, Client/Server Scripts
  - Print Formats, Reports, Workflows, Notifications, Email Templates
  - Dashboards, Dashboard Charts, Number Cards
  - Roles, Letter Heads, Terms & Conditions, Address Templates
  - Workspaces (shortcuts + link cards + content)
  - All Settings singletons (System, Stock, Selling, Buying, Accounts, etc.)
"""

import requests
import json
import sys
import time

requests.packages.urllib3.disable_warnings()

POC_URL  = "http://3.216.86.193"
PROD_URL = "https://www.karavanimports.com"
ADMIN_PASS = os.environ.get("ERP_ADMIN_PWD")

# ---------------------------------------------------------------------------
# List-style doctypes: fetch all docs, push each one to prod
# ---------------------------------------------------------------------------
LIST_DOCTYPES = [
    # Core customization
    "Custom Field",
    "Property Setter",
    "Client Script",
    "Server Script",
    # Workflow
    "Workflow",
    "Workflow State",
    "Workflow Action Master",
    # Notifications & email
    "Notification",
    "Email Template",
    # Print & reports
    "Print Format",
    "Print Style",
    "Report",
    # Roles
    "Role",
    "Role Profile",
    # Dashboards & cards
    "Dashboard",
    "Dashboard Chart",
    "Number Card",
    # Web
    "Web Form",
    "Web Page",
    "Web Template",
    # Misc
    "Letter Head",
    "Terms and Conditions",
    "Address Template",
    "Workspace",
]

# ---------------------------------------------------------------------------
# Singleton doctypes: the doc name == the doctype name
# ---------------------------------------------------------------------------
SINGLETON_DOCTYPES = [
    "System Settings",
    "Global Defaults",
    "Stock Settings",
    "Selling Settings",
    "Buying Settings",
    "Accounts Settings",
    "HR Settings",
    "Manufacturing Settings",
    "CRM Settings",
    "ERPNext Settings",
    "Portal Settings",
    "Website Settings",
    "Social Share Image",
    "Subscription Settings",
    "Asset Settings",
    "Quality Management Settings",
]

# Fields that should never be overwritten on prod
SKIP_FIELDS = {
    "name", "creation", "modified", "modified_by", "owner",
    # keep prod's own DB/server config
    "db_name", "db_password", "db_host",
}

# Built-in roles that already exist — skip creating them to avoid conflicts
BUILTIN_ROLES = {
    "System Manager", "Administrator", "Guest", "All", "Desk User",
    "Script Manager", "Report Manager", "Blogger", "Website Manager",
    "Maintenance Manager", "Maintenance User",
}

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def make_session():
    s = requests.Session()
    s.verify = False
    return s

def login(session, url, password):
    r = session.post(f"{url}/api/method/login",
                     data={"usr": "Administrator", "pwd": password},
                     timeout=30)
    r.raise_for_status()
    if r.json().get("message") != "Logged In":
        raise Exception(f"Login failed at {url}: {r.text[:200]}")
    print(f"  Logged in to {url}")

def api_get(session, url, path, params=None):
    r = session.get(f"{url}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def api_put(session, url, path, payload):
    r = session.put(f"{url}{path}", json=payload, timeout=30)
    return r

def api_post(session, url, path, payload):
    r = session.post(f"{url}{path}", json=payload, timeout=30)
    return r

# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------
def get_list(session, url, doctype, extra_filters=None):
    params = {"limit": 500, 'fields': '["name"]'}
    if extra_filters:
        params["filters"] = json.dumps(extra_filters)
    try:
        data = api_get(session, url, f"/api/resource/{requests.utils.quote(doctype)}", params)
        return [row["name"] for row in data.get("data", [])]
    except Exception as e:
        print(f"    [WARN] Could not list {doctype}: {e}")
        return []

def get_doc(session, url, doctype, name):
    path = f"/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(name)}"
    data = api_get(session, url, path)
    return data.get("data", {})

def get_singleton(session, url, doctype):
    path = f"/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(doctype)}"
    try:
        data = api_get(session, url, path)
        return data.get("data", {})
    except Exception as e:
        print(f"    [WARN] Could not fetch singleton {doctype}: {e}")
        return {}

# ---------------------------------------------------------------------------
# Push helpers
# ---------------------------------------------------------------------------
def clean_payload(doc):
    """Remove read-only / server-managed fields before pushing."""
    return {k: v for k, v in doc.items() if k not in SKIP_FIELDS}

def push_doc(session_prod, doctype, doc):
    name = doc.get("name", "")
    payload = clean_payload(doc)
    # Try PUT first
    r = api_put(session_prod, PROD_URL,
                f"/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(name)}",
                payload)
    if r.status_code == 404:
        # Not on prod yet — create it
        r = api_post(session_prod, PROD_URL,
                     f"/api/resource/{requests.utils.quote(doctype)}",
                     payload)
    if r.status_code not in (200, 201):
        raise Exception(f"HTTP {r.status_code}: {r.text[:300]}")
    return r

def push_singleton(session_prod, doctype, doc):
    payload = clean_payload(doc)
    r = api_put(session_prod, PROD_URL,
                f"/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(doctype)}",
                payload)
    if r.status_code not in (200, 201):
        raise Exception(f"HTTP {r.status_code}: {r.text[:300]}")
    return r

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
print("=" * 60)
print("ERPNext Customization Migration: POC -> Production")
print("=" * 60)
print()

poc  = make_session()
prod = make_session()

print("Logging in...")
login(poc,  POC_URL,  ADMIN_PASS)
login(prod, PROD_URL, ADMIN_PASS)
print()

total_ok = 0
total_fail = 0
failures = []

# ---- Singleton settings ---------------------------------------------------
print("--- Settings Singletons ---")
for doctype in SINGLETON_DOCTYPES:
    try:
        doc = get_singleton(poc, POC_URL, doctype)
        if not doc:
            print(f"  [{doctype}] SKIP (not found)")
            continue
        push_singleton(prod, doctype, doc)
        print(f"  [{doctype}] OK")
        total_ok += 1
    except Exception as e:
        msg = str(e)[:120]
        print(f"  [{doctype}] FAIL: {msg}")
        failures.append((doctype, "(singleton)", msg))
        total_fail += 1
    time.sleep(0.05)
print()

# ---- List-style doctypes --------------------------------------------------
for doctype in LIST_DOCTYPES:
    print(f"--- {doctype} ---")
    names = get_list(poc, POC_URL, doctype)

    if not names:
        print(f"  (none found)")
        print()
        continue

    # Special filter: skip built-in roles
    if doctype == "Role":
        names = [n for n in names if n not in BUILTIN_ROLES]

    # Skip standard/system print formats & reports (only migrate custom ones)
    # (standard ones are flags on the doc itself, checked below)

    for name in names:
        try:
            doc = get_doc(poc, POC_URL, doctype, name)

            # Skip standard/system items
            if doctype in ("Print Format", "Report"):
                if doc.get("standard") == "Yes" or doc.get("is_standard") == 1:
                    continue  # built-in, already on prod

            push_doc(prod, doctype, doc)
            print(f"  [{name}] OK")
            total_ok += 1
        except Exception as e:
            msg = str(e)[:120]
            print(f"  [{name}] FAIL: {msg}")
            failures.append((doctype, name, msg))
            total_fail += 1
        time.sleep(0.05)
    print()

# ---- Summary --------------------------------------------------------------
print("=" * 60)
print(f"DONE: {total_ok} succeeded, {total_fail} failed")
if failures:
    print("\nFailed items:")
    for dt, name, err in failures:
        print(f"  [{dt}] {name}: {err}")
print("=" * 60)
