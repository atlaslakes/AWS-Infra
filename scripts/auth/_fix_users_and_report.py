import os
import requests, json
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

# ── 1. Upgrade Website Users to System Users ──────────────────────────────────
UPGRADE = [
    "karavanimports@atlaslakes.com",
    "omar@atlaslakes.com",
    "youssef@atlaslakes.com",
]

for email in UPGRADE:
    r = s.get(f"{URL}/api/resource/User/{requests.utils.quote(email, safe='')}",
              timeout=15)
    if r.status_code != 200:
        print(f"  SKIP {email}: {r.status_code}")
        continue
    user = r.json().get("data", {})
    profile = user.get("role_profile_name") or ""
    current_type = user.get("user_type")
    if current_type == "System User":
        print(f"  {email} already System User")
        continue

    # Build existing roles list (keep them), add System Manager if none
    roles = [{"role": rr["role"]} for rr in user.get("roles", [])]
    role_names = {rr["role"] for rr in roles}
    if not role_names:
        roles = [{"role": "System Manager"}]

    payload = {"user_type": "System User", "roles": roles}
    if profile:
        payload["role_profile_name"] = profile

    r2 = s.put(f"{URL}/api/resource/User/{requests.utils.quote(email, safe='')}",
               json=payload, timeout=15)
    if r2.status_code in (200, 201):
        print(f"  {email} -> System User  (profile:{profile})")
    else:
        print(f"  ERR {email}: {r2.status_code} {r2.text[:200]}")

print()

# ── 2. Fix Inventory Manager report: cases_on_hand = actual_qty / items_per_case ──
print("=== Fixing Inventory Manager report ===")

report_script = (
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
    '            ROUND(\n'
    '                COALESCE(SUM(b.actual_qty), 0)\n'
    '                / NULLIF(CAST(i.items_per_case AS DECIMAL(10,4)), 0),\n'
    '            2) AS cases_on_hand\n'
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

report_filters = json.dumps([
    {"fieldname": "item_group", "label": "Category", "fieldtype": "Link", "options": "Item Group", "width": 200},
    {"fieldname": "brand",      "label": "Brand",    "fieldtype": "Link", "options": "Brand",      "width": 200},
    {"fieldname": "search",     "label": "Search",   "fieldtype": "Data",                           "width": 200},
])

payload = {
    "report_name": "Inventory Manager",
    "ref_doctype": "Item",
    "report_type": "Script Report",
    "is_standard": "No",
    "module":      "Stock",
    "script":      report_script,
    "filters":     report_filters,
}

r = s.put(f"{URL}/api/resource/Report/Inventory%20Manager", json=payload, timeout=30)
if r.status_code in (200, 201):
    print("  Report updated — Cases On Hand now shows actual cases (units / items_per_case)")
else:
    # Try create
    r2 = s.post(f"{URL}/api/resource/Report", json=payload, timeout=30)
    if r2.status_code in (200, 201):
        print("  Report created OK")
    else:
        print(f"  FAIL {r.status_code}: {r.text[:300]}")

print("\nDone.")
