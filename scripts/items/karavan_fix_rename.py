import os
"""
Fix: rename remaining items (those still using old UPC codes as item_code).
Detects already-renamed items, avoids collisions, and creates the report.
"""
import requests, json, re, time

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
FORMATTED = re.compile(r'^([A-Z]+)-(\d{4})$')

s = requests.Session(); s.verify = False
s.post(f"{PROD_URL}/api/method/login",
       data={"usr": "Administrator", "pwd": PASS}, timeout=20)
print("Logged in")

# ── fetch all items ────────────────────────────────────────────────────────────
r = s.get(f"{PROD_URL}/api/resource/Item",
          params={"limit": 500, "fields": '["name","item_group","item_name"]'}, timeout=30)
items = r.json().get("data", [])
print(f"{len(items)} items total")

# ── split: already done vs still needs rename ──────────────────────────────────
done   = []   # (abbr, number, item_name)
to_do  = []   # (old_code, item_group, item_name)

for it in items:
    m = FORMATTED.match(it["name"])
    if m:
        done.append((m.group(1), int(m.group(2)), it.get("item_name", "")))
    else:
        to_do.append((it["name"], it.get("item_group") or "General", it.get("item_name", "")))

print(f"Already renamed: {len(done)}  |  Still to rename: {len(to_do)}")

# ── determine next counter per prefix ─────────────────────────────────────────
counters = {}
for abbr, num, _ in done:
    counters[abbr] = max(counters.get(abbr, 0), num)

# ── sort to_do by group then name for consistent ordering ─────────────────────
to_do.sort(key=lambda x: (x[1], x[2].lower()))

# ── build rename pairs (collision-safe) ───────────────────────────────────────
all_existing = {it["name"] for it in items}
renames = []
for old, group, name in to_do:
    abbr = GROUP_ABBR.get(group, "GEN")
    counters[abbr] = counters.get(abbr, 0) + 1
    new  = f"{abbr}-{counters[abbr]:04d}"
    while new in all_existing:          # skip if target already taken
        counters[abbr] += 1
        new = f"{abbr}-{counters[abbr]:04d}"
    all_existing.add(new)
    renames.append((old, new, name))

print(f"{len(renames)} renames queued\n")

# ── rename ─────────────────────────────────────────────────────────────────────
ok = fail = 0
for old, new, name in renames:
    r = s.post(f"{PROD_URL}/api/method/frappe.client.rename_doc",
               json={"doctype": "Item", "old_name": old, "new_name": new, "merge": False},
               timeout=60)
    if r.status_code == 200:
        print(f"  {old:40s} -> {new}  ({name[:40]})")
        ok += 1
    else:
        print(f"  ERR {old} -> {new}: {r.status_code} {r.text[:100]}")
        fail += 1
    time.sleep(0.08)

print(f"\nRenamed: {ok} OK, {fail} failed")

# ── create / update Inventory Manager Report ───────────────────────────────────
print("\nCreating Inventory Manager report...")

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
    '        conds.append("(i.item_code LIKE %(search_like)s OR i.item_name LIKE %(search_like)s)")\n'
    '        f["search_like"] = "%" + f["search"] + "%"\n'
    '    where = "WHERE " + " AND ".join(conds)\n'
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
    '    data = frappe.db.sql(sql, f, as_dict=True)\n'
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

# In Frappe v15 Report.filters is a child table, not a JSON string
report_filters_table = [
    {"fieldname": "item_group", "label": "Category",  "fieldtype": "Link", "options": "Item Group", "width": 200},
    {"fieldname": "brand",      "label": "Brand",     "fieldtype": "Link", "options": "Brand",       "width": 200},
    {"fieldname": "search",     "label": "Search",    "fieldtype": "Data",                            "width": 200},
]

payload = {
    "report_name": "Inventory Manager",
    "ref_doctype": "Item",
    "report_type": "Script Report",
    "is_standard": "No",
    "module":      "Stock",
    "script":      script,
    "filters":     report_filters_table,
}

r = s.post(f"{PROD_URL}/api/resource/Report", json=payload, timeout=60)
if r.status_code in (200, 201):
    print(f"  Report created: {r.json().get('data',{}).get('name')}")
else:
    r2 = s.put(f"{PROD_URL}/api/resource/Report/Inventory%20Manager", json=payload, timeout=60)
    if r2.status_code in (200, 201):
        print("  Report updated OK")
    else:
        print(f"  Report FAIL: {r.status_code} {r.text[:300]}")
        # Try without filters
        payload2 = {k: v for k, v in payload.items() if k != "filters"}
        r3 = s.put(f"{PROD_URL}/api/resource/Report/Inventory%20Manager", json=payload2, timeout=60)
        print(f"  Retry without filters: {r3.status_code}")

# ── workspace shortcut ─────────────────────────────────────────────────────────
print("\nAdding shortcut to Stock workspace...")
try:
    ws = s.get(f"{PROD_URL}/api/resource/Workspace/Stock", timeout=30).json().get("data", {})
    def strip(rows):
        skip = {"name","creation","modified","modified_by","owner","parent","parenttype","parentfield"}
        return [{k: v for k, v in row.items() if k not in skip} for row in rows]
    shortcuts = ws.get("shortcuts", [])
    if not any(sh.get("label") == "Inventory Manager" for sh in shortcuts):
        content = json.loads(ws.get("content") or "[]")
        content.insert(0, {"type": "shortcut", "data": {"shortcut_name": "Inventory Manager", "col": 3}})
        r = s.put(f"{PROD_URL}/api/resource/Workspace/Stock", json={
            "shortcuts": strip(shortcuts) + [{"label": "Inventory Manager", "type": "Report",
                                               "link_to": "Inventory Manager", "color": "#2490ef"}],
            "links":     strip(ws.get("links", [])),
            "content":   json.dumps(content),
        }, timeout=30)
        print(f"  Done ({r.status_code})")
    else:
        print("  Already present")
except Exception as e:
    print(f"  Skipped: {e}")

print("\nDone! Go to Stock -> Reports -> Inventory Manager")
