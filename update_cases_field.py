import os
"""
1. Creates custom Int field `cases_on_hand` on Item doctype (if not exists).
2. Populates it from Excel (Karavan Inventory-updated.xlsx) matched by UPC.
3. Updates Inventory Manager report script to read from i.cases_on_hand directly.
"""
import requests, openpyxl, json
requests.packages.urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")


# ── 1. Ensure custom field exists ─────────────────────────────────────────────
print("=== [1] Custom field ===")
cf_check = s.get(f"{URL}/api/resource/Custom Field",
                 params={"filters": '[["dt","=","Item"],["fieldname","=","cases_on_hand"]]',
                         "fields": '["name"]'}, timeout=15)
existing = cf_check.json().get("data", [])
if existing:
    print(f"  Already exists: {existing[0]['name']}")
else:
    r = s.post(f"{URL}/api/resource/Custom Field", json={
        "dt":           "Item",
        "fieldname":    "cases_on_hand",
        "label":        "Cases On Hand",
        "fieldtype":    "Int",
        "insert_after": "standard_rate",
        "in_list_view": 0,
    }, timeout=30)
    if r.status_code in (200, 201):
        print(f"  Created: {r.json()['data']['name']}")
    else:
        print(f"  FAILED {r.status_code}: {r.text[:200]}")
        exit(1)


# ── 2. Load Excel UPC → cases map ─────────────────────────────────────────────
print("\n=== [2] Loading Excel ===")
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx",
                             read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).replace("\n", " ").strip() if h else "" for h in rows[0]]

xl_by_upc = {}
for row in rows[1:]:
    d = dict(zip(headers, row))
    upc_raw = d.get("UPC")
    if isinstance(upc_raw, float): upc = str(int(upc_raw))
    elif upc_raw: upc = str(upc_raw).strip().split(".")[0]
    else: upc = ""
    if not upc or upc == "None": continue
    cases_raw = 0
    for k, v in d.items():
        if "cases" in k.lower() and "hand" in k.lower():
            cases_raw = v
    try: cases = int(float(cases_raw)) if cases_raw else 0
    except: cases = 0
    xl_by_upc[upc] = cases

print(f"  {len(xl_by_upc)} UPC entries from Excel")


# ── 3. Load barcodes ──────────────────────────────────────────────────────────
print("\n=== [3] Loading barcodes ===")
with open("_barcodes.json") as f:
    bc_data = json.load(f)
item_barcodes = {}
for b in bc_data:
    item_barcodes.setdefault(b["item_code"], []).append(str(b["barcode"]).strip())
print(f"  {len(item_barcodes)} items with barcodes")


# ── 4. Update each item ────────────────────────────────────────────────────────
print("\n=== [4] Updating items ===")
erp_items = []
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item",
              params={"fields": '["name","item_name"]',
                      "limit": 100, "limit_start": page * 100}, timeout=30)
    batch = r.json().get("data", [])
    if not batch: break
    erp_items.extend(batch)
    page += 1

matched = updated = skipped = 0
unmatched_items = []
for item in erp_items:
    item_code = item["name"]
    barcodes = item_barcodes.get(item_code, [])
    cases = None
    for bc in barcodes:
        if bc in xl_by_upc:
            cases = xl_by_upc[bc]
            break
    if cases is None:
        unmatched_items.append(item_code)
        continue
    matched += 1
    r = s.post(f"{URL}/api/method/frappe.client.set_value",
               json={"doctype": "Item", "name": item_code,
                     "fieldname": "cases_on_hand", "value": cases},
               timeout=15)
    if r.status_code in (200, 201):
        updated += 1
    else:
        print(f"  ERR {item_code}: {r.status_code} {r.text[:100]}")
    if updated % 50 == 0 and updated > 0:
        print(f"  {updated} updated...")

print(f"  Matched & updated : {updated}")
print(f"  Unmatched (no UPC): {len(unmatched_items)}")
if unmatched_items:
    print(f"  Unmatched items: {unmatched_items[:10]}")


# ── 5. Update report script ───────────────────────────────────────────────────
print("\n=== [5] Updating report script ===")
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
    '            COALESCE(i.cases_on_hand, 0)            AS cases_on_hand\n'
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
    '    ]\n'
    '    return columns, data\n'
)

r = s.post(f"{URL}/api/method/frappe.client.set_value",
           json={"doctype": "Report", "name": "Inventory Manager",
                 "fieldname": "script", "value": script}, timeout=30)
print(f"  Report: {r.status_code} {'OK' if r.status_code in (200,201) else r.text[:150]}")

print("\nDONE — refresh the Inventory Manager report to see integer Cases On Hand.")
