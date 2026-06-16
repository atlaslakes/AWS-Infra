"""
Pangea POS Data → ERPNext Item Import
Reads Sheet1, creates Item Groups + UOMs, then bulk-imports all items.
"""

import openpyxl
import requests
import json
import sys
import time
from collections import Counter

# ── Config ────────────────────────────────────────────────────────────────────
ERPNEXT_URL    = "http://atlaslakeserp"
API_KEY        = "647f56b706a1bea"
API_SECRET     = "6c615d3ea8cbd4d"
EXCEL_FILE     = "C:/Users/aizen/Desktop/Pangea POS Data.xlsx"
BATCH_SIZE     = 25      # items per batch before pausing
DEFAULT_GROUP  = "General Merchandise"

SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"token {API_KEY}:{API_SECRET}"})
SESSION.verify = False   # self-signed cert

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── UOM mapping from Excel → ERPNext ─────────────────────────────────────────
UOM_MAP = {
    None:  "Nos",
    "LB":  "lb",
    "lb":  "lb",
    "EA":  "Nos",
    "EACH":"Nos",
}


# ── ERPNext helpers ───────────────────────────────────────────────────────────

def erp_exists(doctype: str, name: str) -> bool:
    r = SESSION.get(
        f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(name)}",
        timeout=10
    )
    return r.status_code == 200


def erp_create(doctype: str, doc: dict) -> dict:
    r = SESSION.post(
        f"{ERPNEXT_URL}/api/resource/{doctype}",
        json=doc, timeout=15
    )
    if r.status_code in (200, 201):
        return r.json()
    raise RuntimeError(f"{doctype} create failed {r.status_code}: {r.text[:300]}")


def ensure_uom(uom_name: str):
    if not erp_exists("UOM", uom_name):
        erp_create("UOM", {"doctype": "UOM", "uom_name": uom_name})
        print(f"  Created UOM: {uom_name}")
    else:
        print(f"  UOM exists: {uom_name}")


def ensure_item_group(group_name: str):
    if not erp_exists("Item Group", group_name):
        erp_create("Item Group", {
            "doctype": "Item Group",
            "item_group_name": group_name,
            "parent_item_group": "All Item Groups",
            "is_group": 0,
        })
        print(f"  Created Item Group: {group_name}")


# ── Load Excel ────────────────────────────────────────────────────────────────

print("Loading Excel...")
wb = openpyxl.load_workbook(EXCEL_FILE)
ws = wb['Sheet1']

rows = []
for row in ws.iter_rows(min_row=2, values_only=True):
    code, name, group, price, uom = row
    if not code or not name:
        continue
    rows.append({
        "code":  str(code).strip(),
        "name":  str(name).strip(),
        "group": str(group).strip() if group else DEFAULT_GROUP,
        "price": float(price) if price and str(price).strip().upper() != "NULL" else 0.0,
        "uom":   UOM_MAP.get(uom, "Nos"),
    })

print(f"Loaded {len(rows)} items from Excel")

# ── Ensure UOMs and Item Groups exist ─────────────────────────────────────────

print("\n--- Ensuring UOMs ---")
for uom in {"Nos", "lb"}:
    ensure_uom(uom)

print("\n--- Ensuring Item Groups ---")
groups_needed = set(r["group"] for r in rows)
for g in sorted(groups_needed):
    ensure_item_group(g)

# ── Check which items already exist ──────────────────────────────────────────

print("\n--- Checking existing items ---")
existing_r = SESSION.get(
    f"{ERPNEXT_URL}/api/resource/Item",
    params={"fields": '["item_code"]', "limit_page_length": 99999},
    timeout=30
)
existing_codes = set()
if existing_r.status_code == 200:
    for d in existing_r.json().get("data", []):
        existing_codes.add(d["item_code"])
print(f"  {len(existing_codes)} items already in ERPNext")

to_import = [r for r in rows if r["code"] not in existing_codes]
print(f"  {len(to_import)} items to import")

# ── Import items ──────────────────────────────────────────────────────────────

print("\n--- Importing items ---")
created = 0
skipped = 0
errors  = []

for i, item in enumerate(to_import, 1):
    doc = {
        "doctype":      "Item",
        "item_code":    item["code"],
        "item_name":    item["name"],
        "item_group":   item["group"],
        "stock_uom":    item["uom"],
        "is_stock_item": 1,
        "is_sales_item": 1,
        "standard_rate": item["price"],
    }
    try:
        erp_create("Item", doc)
        created += 1
    except RuntimeError as e:
        err_str = str(e)
        # If duplicate, just skip
        if "DuplicateEntryError" in err_str or "already exists" in err_str.lower():
            skipped += 1
        else:
            errors.append({"code": item["code"], "error": err_str})
            if len(errors) <= 5:
                print(f"  ERROR {item['code']}: {err_str[:120]}")

    if i % BATCH_SIZE == 0:
        pct = i / len(to_import) * 100
        print(f"  Progress: {i}/{len(to_import)} ({pct:.0f}%) — created {created}, skipped {skipped}, errors {len(errors)}")
        time.sleep(1.5)  # longer pause to avoid overwhelming the server

# ── Summary ───────────────────────────────────────────────────────────────────

print(f"""
=== Import Complete ===
Created : {created}
Skipped : {skipped}
Errors  : {len(errors)}
""")

if errors:
    print("First 20 errors:")
    for e in errors[:20]:
        print(f"  {e['code']}: {e['error'][:100]}")

    with open("scripts/import_errors.json", "w") as f:
        json.dump(errors, f, indent=2)
    print(f"\nAll errors saved to scripts/import_errors.json")
