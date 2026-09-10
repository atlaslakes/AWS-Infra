import os
"""
Keeps Item.valuation_rate (cost) and Item Price (Standard Selling) in
sync with the stock ledger, via a scheduled job rather than DocType
Event hooks.

Item.cases_on_hand (a Custom Field) was retired -- Custom Fields get
serialized into every Item REST response, which isn't wanted. Stock is
now shown directly from the core, non-custom Bin.actual_qty, computed
live in the Inventory Manager report (see _update_inventory_manager_query.py)
rather than mirrored into a separate field.

Supersedes the Bin/Stock Ledger Entry hook-based scripts
(_sync_cases_on_hand_to_bin.py, the "Sync Item Cost - Bin" script in
setup_cost_margin_pricing.py) -- both are now disabled. Neither hook
point turned out reliable:
  - Bin "After Save" never fires: every real stock-affecting document
    (Sales Invoice with Update Stock, Stock Reconciliation, Stock Entry)
    updates Bin.actual_qty/valuation_rate via internal bulk SQL, not
    Bin.save().
  - Stock Ledger Entry "After Insert" fires too early relative to Bin
    being updated, AND on cancellation ERPNext flips is_cancelled=1 on
    existing SLE rows rather than cleanly appending a reversal, so
    "latest SLE by creation" for an item can read a stale or wrong row.
    Confirmed by testing: a Sales Invoice submit/cancel cycle produced
    cases_on_hand=0 and other wrong values with the SLE-hook approach.

Bin is the one place ERPNext guarantees to be correct once a
transaction completes (verified: qty moved 23 -> 22 -> 23 correctly
across submit/cancel in testing) -- it's just not update()-hook-friendly.
So this re-derives cases_on_hand/cost/price from Bin on a fixed
schedule instead of chasing document-event timing.

Creates one Server Script, "Sync Item Stock And Price - Scheduled"
(Scheduler Event, Cron "* * * * *" -- every minute, the finest
granularity Frappe's cron scheduler supports). Confirmed end-to-end:
after a real invoice submit, the *unattended* cron run correctly
synced cost within its next tick (~1 minute).

"Sync Item Price - Margin Change" (Pricing Rule, After Save) is left
as-is -- editing a Pricing Rule IS a normal doc.save(), so that hook
fires reliably and doesn't need the scheduled fallback.

Run once against the site:
    ERP_ADMIN_USR=... ERP_ADMIN_PWD=... python setup_stock_price_scheduled_sync.py
"""

import requests, sys
requests.packages.urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
s = requests.Session(); s.verify = False

login_resp = s.post(f"{URL}/api/method/login",
                     data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"),
                           "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
if login_resp.status_code != 200:
    print(f"Login failed {login_resp.status_code}: {login_resp.text[:300]}")
    sys.exit(1)

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
        update(dt, name, doc)
        print(f"  updated : {dt} / {name}")
    else:
        create(dt, doc)
        print(f"  created : {dt} / {name}")

print("=== Disabling unreliable hook-based sync scripts ===")
for name in ("Sync Cases On Hand - Bin", "Sync Item Cost - Bin"):
    if exists("Server Script", name):
        update("Server Script", name, {"disabled": 1})
        print(f"  disabled: Server Script / {name}")

sync_script = """
items = frappe.db.sql("SELECT name FROM `tabItem`", as_list=True)
for (code,) in items:
    row = frappe.db.sql(
        "SELECT SUM(actual_qty * valuation_rate) / NULLIF(SUM(actual_qty), 0) AS wavg "
        "FROM `tabBin` WHERE item_code=%s AND actual_qty > 0",
        (code,), as_dict=True
    )[0]
    cost = row["wavg"] or 0

    if cost > 0:
        frappe.db.set_value("Item", code, "valuation_rate", cost, update_modified=False)
        rule = frappe.db.get_value(
            "Pricing Rule", {"title": "Margin - " + code},
            ["margin_type", "margin_rate_or_amount"], as_dict=True
        )
        if rule and rule.margin_type:
            margin = rule.margin_rate_or_amount or 0
            new_price = cost * (1 + margin / 100) if rule.margin_type == "Percentage" else cost + margin
            existing = frappe.db.get_value(
                "Item Price",
                {"item_code": code, "price_list": "Standard Selling", "selling": 1},
                "name",
            )
            if existing:
                frappe.db.set_value("Item Price", existing, "price_list_rate", new_price, update_modified=False)
            else:
                try:
                    frappe.get_doc({
                        "doctype": "Item Price", "item_code": code, "price_list": "Standard Selling",
                        "selling": 1, "price_list_rate": new_price,
                    }).insert(ignore_permissions=True)
                except Exception:
                    pass

frappe.db.commit()
"""

print("\n=== Scheduled sync: cost / selling price ===")
upsert("Server Script", "Sync Item Stock And Price - Scheduled", {
    "doctype": "Server Script",
    "name": "Sync Item Stock And Price - Scheduled",
    "script_type": "Scheduler Event",
    "event_frequency": "Cron",
    "cron_format": "* * * * *",
    "disabled": 0,
    "script": sync_script,
})

print("\nDone. cost/selling price now resync from Bin every minute.")
