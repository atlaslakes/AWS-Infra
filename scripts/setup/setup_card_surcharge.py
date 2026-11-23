"""
Creates the native ERPNext Account the Stripe webhook books credit-card
surcharges to ("Credit Card Surcharge Income", under the company's Indirect
Income group). No custom fields — the surcharge rides on the standard
Payment Entry "Deductions or Loss" table.

Idempotent. Dry-run by default; pass --apply to create.

    ERPNEXT_API_KEY=... ERPNEXT_API_SECRET=... python setup_card_surcharge.py [--apply]
    (optional) ERPNEXT_COMPANY="Karavan Imports"  ACCOUNT_NAME="Credit Card Surcharge Income"
"""

import json
import os
import sys

import requests

URL = os.environ.get("ERPNEXT_URL", "https://erpnext.karavanimports.com").rstrip("/")
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME", "Credit Card Surcharge Income")
APPLY = "--apply" in sys.argv

key, secret = os.environ.get("ERPNEXT_API_KEY"), os.environ.get("ERPNEXT_API_SECRET")
if not (key and secret):
    sys.exit("Set ERPNEXT_API_KEY and ERPNEXT_API_SECRET")

s = requests.Session()
s.headers["Authorization"] = f"token {key}:{secret}"


def get_list(doctype, filters, fields):
    r = s.get(f"{URL}/api/resource/{doctype}",
              params={"filters": json.dumps(filters), "fields": json.dumps(fields), "limit_page_length": 50},
              timeout=20)
    r.raise_for_status()
    return r.json()["data"]


companies = get_list("Company", [], ["name", "abbr"])
company = os.environ.get("ERPNEXT_COMPANY") or (companies[0]["name"] if len(companies) == 1 else None)
if not company:
    sys.exit(f"Multiple companies {[c['name'] for c in companies]}; set ERPNEXT_COMPANY")
print(f"Company: {company}")

existing = get_list("Account", [["account_name", "=", ACCOUNT_NAME], ["company", "=", company]], ["name"])
if existing:
    print(f"Already exists: {existing[0]['name']}")
    sys.exit(0)

parents = get_list("Account", [["company", "=", company], ["is_group", "=", 1], ["root_type", "=", "Income"],
                               ["account_name", "in", ["Indirect Income", "Direct Income", "Income"]]],
                   ["name", "account_name"])
by_name = {p["account_name"]: p["name"] for p in parents}
parent = by_name.get("Indirect Income") or by_name.get("Direct Income") or by_name.get("Income")
if not parent:
    sys.exit("No Income group account found; create the account manually in the Chart of Accounts.")

doc = {"doctype": "Account", "account_name": ACCOUNT_NAME, "parent_account": parent,
       "company": company, "root_type": "Income", "report_type": "Profit and Loss", "is_group": 0}
print(f"Will create: {ACCOUNT_NAME} under {parent}")
if not APPLY:
    print("Dry run — re-run with --apply to create.")
    sys.exit(0)

r = s.post(f"{URL}/api/resource/Account", json=doc, timeout=20)
r.raise_for_status()
print(f"Created: {r.json()['data']['name']}")
