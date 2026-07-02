import os
"""
Updates the Inventory Manager report on both ERPNext instances
to include Price/Item and Price/Case columns from Standard Selling price list.
"""
import requests
requests.packages.urllib3.disable_warnings()

INSTANCES = [
    "https://www.karavanimports.com",
    "http://3.216.86.193",
]
PASS = os.environ.get("ERP_ADMIN_PWD")

NEW_QUERY = """SELECT
    i.item_code       AS "Item ID:Link/Item:130",
    i.item_name       AS "Description:Data:240",
    i.brand           AS "Brand:Link/Brand:150",
    i.item_group      AS "Category:Link/Item Group:155",
    COALESCE(
        (SELECT ib.barcode FROM `tabItem Barcode` ib
         WHERE ib.parent = i.item_code LIMIT 1), "") AS "UPC / Barcode:Data:155",
    COALESCE(i.items_per_case, "")  AS "Items Per Case:Data:120",
    COALESCE(i.package_size, "")    AS "Package Size:Data:110",
    ROUND(COALESCE(SUM(b.actual_qty), 0), 2) AS "Cases On Hand:Float:130",
    ROUND(COALESCE(
        (SELECT ip.price_list_rate
         FROM `tabItem Price` ip
         WHERE ip.item_code = i.item_code
           AND ip.price_list = 'Standard Selling'
         LIMIT 1), 0
    ), 2) AS "Price/Item:Currency:120",
    ROUND(COALESCE(
        (SELECT ip.price_list_rate * COALESCE(i.items_per_case, 1)
         FROM `tabItem Price` ip
         WHERE ip.item_code = i.item_code
           AND ip.price_list = 'Standard Selling'
         LIMIT 1), 0
    ), 2) AS "Price/Case:Currency:120"
FROM `tabItem` i
LEFT JOIN `tabBin` b ON b.item_code = i.item_code
WHERE i.disabled = 0
GROUP BY i.item_code
ORDER BY i.item_group, i.item_name"""

for url in INSTANCES:
    label = "PROD" if "karavan" in url else "STAGING"
    s = requests.Session(); s.verify = False
    s.post(f"{url}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=15)
    r = s.put(f"{url}/api/resource/Report/Inventory%20Manager",
              json={"query": NEW_QUERY, "report_type": "Query Report"},
              timeout=20)
    print(f"[{label}] {r.status_code}")
    if r.status_code != 200:
        print(" ", r.text[:200])
