import os
"""
SUPERSEDED by setup_stock_price_scheduled_sync.py -- the SLE "After
Insert" hook this script creates turned out unreliable (timing/
is_cancelled quirks around document cancellation). The Server Script
this creates is now disabled on the live site. Kept for history.

Keeps Item.cases_on_hand in sync with the stock ledger going forward.

Creates a Server Script on Stock Ledger Entry (After Insert) that
recomputes SUM(Bin.actual_qty) for the affected item and writes it to
Item.cases_on_hand -- i.e. cases_on_hand becomes a live mirror instead
of a point-in-time snapshot.

Hooked on Stock Ledger Entry, not Bin: every real stock movement (Sales
Invoice with Update Stock, Stock Reconciliation, Stock Entry, ...)
updates Bin.actual_qty via internal bulk SQL, which never fires a
Bin "After Save" hook. A Stock Ledger Entry is always created through
the ORM (insert()), so it's the one doctype event that reliably fires
for every stock-affecting transaction. (Confirmed by testing: a Sales
Invoice submit correctly moved Bin.actual_qty 23 -> 22, but a
Bin-hooked version of this script never ran.)

Run once against the site:
    ERP_ADMIN_USR=... ERP_ADMIN_PWD=... python _sync_cases_on_hand_to_bin.py
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

SCRIPT_NAME = "Sync Cases On Hand - Bin"

# Reads Stock Ledger Entry directly (latest row per warehouse), not Bin --
# ERPNext inserts the SLE before it applies the resulting change to Bin,
# so a Bin read at "After Insert" time can be one transaction stale.
sync_script = """
rows = frappe.db.sql('''
    SELECT sle.qty_after_transaction AS qty
    FROM `tabStock Ledger Entry` sle
    INNER JOIN (
        SELECT warehouse, MAX(creation) AS max_creation
        FROM `tabStock Ledger Entry`
        WHERE item_code=%s
        GROUP BY warehouse
    ) latest ON latest.warehouse = sle.warehouse AND latest.max_creation = sle.creation
    WHERE sle.item_code=%s
''', (doc.item_code, doc.item_code), as_dict=True)

total = sum(r.qty or 0 for r in rows)
frappe.db.set_value("Item", doc.item_code, "cases_on_hand", round(total), update_modified=False)
"""

upsert("Server Script", SCRIPT_NAME, {
    "doctype": "Server Script",
    "name": SCRIPT_NAME,
    "script_type": "DocType Event",
    "reference_doctype": "Stock Ledger Entry",
    "doctype_event": "After Insert",
    "enabled": 1,
    "script": sync_script,
})

print("\nDone. Item.cases_on_hand now updates automatically whenever a stock movement posts.")
