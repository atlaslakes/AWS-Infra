import os
"""
Keeps the live Inventory Manager report's query in sync with the repo.
Supersedes _update_inventory_manager_cases.py (same mechanism, now also
covers the Cost/Selling Price split and the Cost/Case column).

The live "Inventory Manager" report is a Query Report (SQL lives in the
`query` field), not a Script Report -- despite karavan_inventory_manager.py
creating it as report_type "Script Report" with a `script` field. It was
apparently converted to a Query Report at some point outside this repo
(also gained Price/Case and Nearest Expiry columns not present in that
setup script). This script edits the field that's actually executed.

Column sourcing, current state:
  Stock          <- SUM(tabBin.actual_qty), computed live in this query --
                    NOT a field on Item. The cases_on_hand Custom Field was
                    removed (Custom Fields get serialized into every Item
                    REST response, which wasn't wanted); Bin is already a
                    core, non-custom table and was always the real source
                    of truth cases_on_hand mirrored.
  Cost           <- Item.valuation_rate (core field), synced by the
                    "Sync Item Stock And Price - Scheduled" Server Script
                    (scripts/inventory/setup_stock_price_scheduled_sync.py)
  Selling Price  <- Item Price (Standard Selling).price_list_rate, derived
                    from Cost + that item's "Margin - <item_code>" Pricing
                    Rule, kept live by the same scheduled script plus
                    "Sync Item Price - Margin Change"

Run once against the site:
    ERP_ADMIN_USR=... ERP_ADMIN_PWD=... python _update_inventory_manager_query.py
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

new_query = """SELECT
    i.item_code       AS "Item ID:Link/Item:130",
    i.item_name       AS "Description:Data:240",
    i.brand           AS "Brand:Link/Brand:150",
    i.item_group      AS "Category:Link/Item Group:155",
    COALESCE(
        (SELECT ib.barcode FROM `tabItem Barcode` ib
         WHERE ib.parent = i.item_code LIMIT 1), "") AS "UPC / Barcode:Data:155",
    COALESCE(i.items_per_case, "")  AS "Items Per Case:Data:120",
    COALESCE(i.package_size, "")    AS "Package Size:Data:110",
    COALESCE(
        (SELECT SUM(b.actual_qty) FROM `tabBin` b WHERE b.item_code = i.item_code), 0
    ) AS "Stock:Int:130",
    ROUND(COALESCE(i.valuation_rate, 0), 2) AS "Cost:Currency:120",
    ROUND(COALESCE(i.valuation_rate, 0) * COALESCE(i.items_per_case, 1), 2) AS "Cost/Case:Currency:120",
    ROUND(COALESCE(
        (SELECT ip.price_list_rate FROM `tabItem Price` ip
         WHERE ip.item_code = i.item_code AND ip.price_list = 'Standard Selling'
         LIMIT 1), 0), 2) AS "Selling Price:Currency:120",
    ROUND(COALESCE(
        (SELECT ip.price_list_rate * COALESCE(i.items_per_case, 1)
         FROM `tabItem Price` ip
         WHERE ip.item_code = i.item_code AND ip.price_list = 'Standard Selling'
         LIMIT 1), 0), 2) AS "Price/Case:Currency:120",
    (
        SELECT MIN(il.expiry_date)
        FROM `tabItem Lot` il
        WHERE il.item_code = i.item_code
          AND il.expiry_date >= CURDATE()
    ) AS "Nearest Expiry:Date:120"
FROM `tabItem` i
WHERE i.disabled = 0
ORDER BY i.item_group, i.item_name"""

r = s.put(f"{URL}/api/resource/Report/Inventory%20Manager", json={"query": new_query}, timeout=30)
if r.status_code in (200, 201):
    print("Report updated OK")
else:
    print(f"FAILED {r.status_code}: {r.text[:300]}")
    sys.exit(1)
