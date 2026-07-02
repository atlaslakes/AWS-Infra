import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Report reads cases_on_hand directly from the Item custom field
script = (
    'import frappe\n'
    '\n'
    'def execute(filters=None):\n'
    '    f = dict(filters or {})\n'
    '    conds = ["i.disabled = 0"]\n'
    '    if f.get("item_group"):\n'
    '        conds.append("i.item_group = %(item_group)s")\n'
    '    if f.get("brand"):\n'
    '        conds.append("i.brand = %(brand)s")\n'
    '    if f.get("search"):\n'
    '        conds.append("(i.item_code LIKE %(search)s OR i.item_name LIKE %(search)s)")\n'
    '        f["search"] = "%" + f["search"] + "%"\n'
    '    where = "WHERE " + " AND ".join(conds)\n'
    '\n'
    '    sql = """\n'
    '        SELECT\n'
    '            i.item_code                             AS item_code,\n'
    '            i.item_name                             AS item_name,\n'
    '            i.brand                                 AS brand,\n'
    '            i.item_group                            AS item_group,\n'
    '            COALESCE(\n'
    '                (SELECT ib.barcode FROM `tabItem Barcode` ib\n'
    '                 WHERE ib.parent = i.item_code LIMIT 1), "") AS upc,\n'
    '            COALESCE(i.items_per_case, "")          AS items_per_case,\n'
    '            COALESCE(i.package_size, "")            AS package_size,\n'
    '            COALESCE(i.cases_on_hand, 0)            AS cases_on_hand,\n'
    '            COALESCE(i.stock, 0)                    AS stock\n'
    '        FROM `tabItem` i\n'
    '        {where}\n'
    '        ORDER BY i.item_group, i.item_name\n'
    '    """.format(where=where)\n'
    '\n'
    '    data = frappe.db.sql(sql, f, as_dict=True)\n'
    '\n'
    '    columns = [\n'
    '        {"label": "Item ID",        "fieldname": "item_code",      "fieldtype": "Link",  "options": "Item",       "width": 130},\n'
    '        {"label": "Description",    "fieldname": "item_name",      "fieldtype": "Data",                           "width": 240},\n'
    '        {"label": "Brand",          "fieldname": "brand",          "fieldtype": "Link",  "options": "Brand",      "width": 150},\n'
    '        {"label": "Category",       "fieldname": "item_group",     "fieldtype": "Link",  "options": "Item Group", "width": 150},\n'
    '        {"label": "UPC / Barcode",  "fieldname": "upc",            "fieldtype": "Data",                           "width": 155},\n'
    '        {"label": "Items Per Case", "fieldname": "items_per_case", "fieldtype": "Data",                           "width": 120},\n'
    '        {"label": "Package Size",   "fieldname": "package_size",   "fieldtype": "Data",                           "width": 110},\n'
    '        {"label": "Cases On Hand",  "fieldname": "cases_on_hand",  "fieldtype": "Int",                            "width": 130},\n'
    '        {"label": "Stock",          "fieldname": "stock",          "fieldtype": "Int",                            "width": 100},\n'
    '    ]\n'
    '    return columns, data\n'
)

r = s.post(f"{URL}/api/method/frappe.client.set_value",
           json={"doctype": "Report", "name": "Inventory Manager",
                 "fieldname": "script", "value": script},
           timeout=30)
print("Report:", r.status_code, "OK" if r.status_code in (200,201) else r.text[:150])
