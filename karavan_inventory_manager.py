import os
"""
Karavan Imports - Inventory Manager Setup
1. Renames Item Code (ID) from UPC -> group-based IDs (RICE-0001, SPICE-0025 ...)
   UPC stays untouched in the barcode field.
2. Creates "Inventory Manager" Script Report with all columns.
3. Adds shortcut to Stock workspace.
"""

import requests, json, time

requests.packages.urllib3.disable_warnings()

PROD_URL = "https://www.karavanimports.com"
PASS     = os.environ.get("ERP_ADMIN_PWD")

GROUP_ABBR = {
    "Rice & Grains":       "RICE",
    "Pasta & Noodles":     "PASTA",
    "Spices & Herbs":      "SPICE",
    "Oils & Ghee":         "OIL",
    "Pickles & Olives":    "PICKLE",
    "Beans & Pulses":      "BEAN",
    "Beverages":           "BEV",
    "Dairy & Cheese":      "DAIRY",
    "Nuts & Seeds":        "NUTS",
    "Snacks & Sweets":     "SNACK",
    "Condiments & Sauces": "COND",
    "Personal Care":       "CARE",
    "Charcoal":            "CHARC",
    "General":             "GEN",
}

s = requests.Session()
s.verify = False

def login():
    r = s.post(f"{PROD_URL}/api/method/login",
               data={"usr": "Administrator", "pwd": PASS}, timeout=20)
    assert r.json().get("message") == "Logged In", r.text[:200]
    print("  Logged in")

def GET(path, **params):
    r = s.get(f"{PROD_URL}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def POST(path, body):
    return s.post(f"{PROD_URL}{path}", json=body, timeout=90)

def PUT(path, body):
    return s.put(f"{PROD_URL}{path}", json=body, timeout=90)

def uq(v):
    return requests.utils.quote(str(v), safe="")

print("=" * 65)
print("  Karavan Imports - Inventory Manager Setup")
print("=" * 65)
login()

# ── 1. Fetch all items ─────────────────────────────────────────────────────────
print("\n[1] Fetching all items...")
r = GET("/api/resource/Item",
        **{"limit": 500, "fields": '["name","item_group","item_name"]'})
items = r.get("data", [])
print(f"  {len(items)} items")
items.sort(key=lambda x: (x.get("item_group", ""), x.get("item_name", "").lower()))

# ── 2. Build rename map ────────────────────────────────────────────────────────
group_counters = {}
used_codes     = set()
renames        = []

for item in items:
    group = item.get("item_group") or "General"
    abbr  = GROUP_ABBR.get(group, "GEN")
    group_counters[abbr] = group_counters.get(abbr, 0) + 1
    new_code = f"{abbr}-{group_counters[abbr]:04d}"
    while new_code in used_codes:
        group_counters[abbr] += 1
        new_code = f"{abbr}-{group_counters[abbr]:04d}"
    used_codes.add(new_code)

    old_code = item["name"]
    if old_code != new_code:
        renames.append((old_code, new_code, item.get("item_name", "")))

print(f"  {len(renames)} items to rename (UPC -> Group ID)")

# ── 3. Rename items ────────────────────────────────────────────────────────────
print("\n[2] Renaming item codes...")
ok = fail = 0
for old, new, name in renames:
    r = POST("/api/method/frappe.client.rename_doc", {
        "doctype":  "Item",
        "old_name": old,
        "new_name": new,
        "merge":    False,
    })
    if r.status_code == 200:
        print(f"  {old:40s} -> {new}  ({name[:40]})")
        ok += 1
    else:
        print(f"  ERR {old} -> {new}: {r.status_code} {r.text[:100]}")
        fail += 1
    time.sleep(0.08)

print(f"\n  Renamed: {ok} OK, {fail} failed")

# ── 4. Create Inventory Manager Script Report ──────────────────────────────────
print("\n[3] Creating Inventory Manager report...")

# Use single-triple-quotes inside so it doesn't collide with this file's quotes
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

report_filters = json.dumps([
    {"fieldname": "item_group", "label": "Category",   "fieldtype": "Link", "options": "Item Group", "width": 200},
    {"fieldname": "brand",      "label": "Brand",      "fieldtype": "Link", "options": "Brand",       "width": 200},
    {"fieldname": "search",     "label": "Search",     "fieldtype": "Data",                            "width": 200},
])

report_payload = {
    "report_name": "Inventory Manager",
    "ref_doctype": "Item",
    "report_type": "Script Report",
    "is_standard": "No",
    "module":      "Stock",
    "script":      report_script,
    "filters":     report_filters,
}

r = POST("/api/resource/Report", report_payload)
if r.status_code in (200, 201):
    print(f"  Created: {r.json().get('data', {}).get('name')}")
else:
    r2 = PUT("/api/resource/Report/Inventory%20Manager", report_payload)
    if r2.status_code in (200, 201):
        print("  Updated OK")
    else:
        print(f"  FAIL: {r.status_code} {r.text[:300]}")

# ── 5. Add shortcut to Stock workspace ────────────────────────────────────────
print("\n[4] Adding shortcut to Stock workspace...")
try:
    ws = GET("/api/resource/Workspace/Stock").get("data", {})

    def strip(rows):
        skip = {"name", "creation", "modified", "modified_by", "owner",
                "parent", "parenttype", "parentfield"}
        return [{k: v for k, v in row.items() if k not in skip} for row in rows]

    shortcuts = ws.get("shortcuts", [])
    if not any(sh.get("label") == "Inventory Manager" for sh in shortcuts):
        new_sc = {
            "label":    "Inventory Manager",
            "type":     "Report",
            "link_to":  "Inventory Manager",
            "color":    "#2490ef",
            "icon":     "table",
        }
        content = json.loads(ws.get("content") or "[]")
        content.insert(0, {"type": "shortcut",
                            "data": {"shortcut_name": "Inventory Manager", "col": 3}})
        r = PUT("/api/resource/Workspace/Stock", {
            "shortcuts": strip(shortcuts) + [new_sc],
            "links":     strip(ws.get("links", [])),
            "content":   json.dumps(content),
        })
        print(f"  Shortcut added ({r.status_code})")
    else:
        print("  Shortcut already present")
except Exception as e:
    print(f"  Workspace step skipped: {e}")

print("\n" + "=" * 65)
print("  DONE.")
print("  -> Stock -> Reports -> Inventory Manager")
print("  -> Or Stock workspace shortcut")
print("=" * 65)
