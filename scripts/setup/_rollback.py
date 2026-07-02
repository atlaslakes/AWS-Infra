import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

# ── 1. Cancel + delete stock reconciliation ───────────────────────────────────
print("=== [1] Rolling back Stock Reconciliation ===")

# Find all submitted stock reconciliations from today
r = s.get(f"{URL}/api/resource/Stock%20Reconciliation",
          params={"fields": '["name","docstatus","posting_date","purpose"]',
                  "filters": '[["posting_date","=","2026-06-26"]]',
                  "limit": 50}, timeout=15)
recons = r.json().get("data", [])
print(f"  Found {len(recons)} reconciliation(s) from today")

for rec in recons:
    name = rec["name"]
    status = rec.get("docstatus", 0)
    print(f"  {name} docstatus={status}")

    if status == 1:  # submitted — cancel first
        rc = s.post(f"{URL}/api/method/frappe.client.cancel",
                    json={"doctype": "Stock Reconciliation", "name": name}, timeout=60)
        if rc.status_code in (200, 201):
            print(f"    Cancelled")
        else:
            print(f"    Cancel failed {rc.status_code}: {rc.text[:150]}")
            continue

    # Delete (draft or just-cancelled)
    rd = s.delete(f"{URL}/api/resource/Stock%20Reconciliation/{name}", timeout=30)
    if rd.status_code in (200, 202, 204):
        print(f"    Deleted")
    else:
        print(f"    Delete failed {rd.status_code}: {rd.text[:150]}")

# ── 2. Revert users back to Website User ──────────────────────────────────────
print("\n=== [2] Reverting users to Website User ===")

REVERT = [
    "karavanimports@atlaslakes.com",
    "omar@atlaslakes.com",
    "youssef@atlaslakes.com",
]

for email in REVERT:
    enc = requests.utils.quote(email, safe="")
    r = s.get(f"{URL}/api/resource/User/{enc}", timeout=15)
    if r.status_code != 200:
        print(f"  SKIP {email}: not found")
        continue
    user = r.json().get("data", {})
    if user.get("user_type") == "Website User":
        print(f"  {email} already Website User")
        continue

    ru = s.put(f"{URL}/api/resource/User/{enc}",
               json={"user_type": "Website User", "roles": []}, timeout=15)
    if ru.status_code in (200, 201):
        print(f"  {email} -> Website User")
    else:
        print(f"  ERR {email}: {ru.status_code} {ru.text[:150]}")

# ── 3. Revert Inventory Manager report script ─────────────────────────────────
print("\n=== [3] Reverting Inventory Manager report ===")

original_script = (
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
    '            i.item_code       AS item_code,\n'
    '            i.item_name       AS item_name,\n'
    '            i.brand           AS brand,\n'
    '            i.item_group      AS item_group,\n'
    '            COALESCE(\n'
    '                (SELECT ib.barcode FROM `tabItem Barcode` ib\n'
    '                 WHERE ib.parent = i.item_code LIMIT 1), "") AS upc,\n'
    '            COALESCE(i.items_per_case, "")  AS items_per_case,\n'
    '            COALESCE(i.package_size, "")    AS package_size,\n'
    '            ROUND(COALESCE(SUM(b.actual_qty), 0), 2) AS cases_on_hand\n'
    '        FROM `tabItem` i\n'
    '        LEFT JOIN `tabBin` b ON b.item_code = i.item_code\n'
    '        {where}\n'
    '        GROUP BY i.item_code\n'
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
    '        {"label": "Cases On Hand",  "fieldname": "cases_on_hand",  "fieldtype": "Float",                          "width": 130},\n'
    '    ]\n'
    '    return columns, data\n'
)

rr = s.post(f"{URL}/api/method/frappe.client.set_value",
            json={"doctype": "Report", "name": "Inventory Manager",
                  "fieldname": "script", "value": original_script},
            timeout=30)
if rr.status_code in (200, 201):
    print("  Report script reverted to original")
else:
    print(f"  ERR {rr.status_code}: {rr.text[:200]}")

print("\n=== Rollback complete ===")
