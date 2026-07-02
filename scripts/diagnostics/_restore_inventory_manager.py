import os, requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

query = """SELECT
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
        (SELECT SUM(b.actual_qty) FROM `tabBin` b
         WHERE b.item_code = i.item_code
           AND b.warehouse = 'Stores - AL'), 0) AS "Cases On Hand:Int:130",
    ROUND(COALESCE(
        (SELECT ip.price_list_rate FROM `tabItem Price` ip
         WHERE ip.item_code = i.item_code AND ip.price_list = 'Standard Selling'
         LIMIT 1), 0), 2) AS "Price/Item:Currency:120",
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

r = s.post(f"{URL}/api/method/frappe.client.set_value",
           json={"doctype": "Report", "name": "Inventory Manager",
                 "fieldname": "query", "value": query}, timeout=30)
print("Report updated:", r.status_code, "OK" if r.status_code in (200, 201) else r.text[:300])
