import os
"""
Sets stock quantities in ERPNext to match Cases On Hand from Karavan Inventory-updated.xlsx.
Matching: UPC/barcode only.
Qty: stored as INTEGER cases (1 Bin unit = 1 case).
"""

import requests, openpyxl
requests.packages.urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")


# ── 1. Load Excel ──────────────────────────────────────────────────────────────
print("=== [1] Loading Excel ===")
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx",
                             read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).replace("\n", " ").strip() if h else "" for h in rows[0]]
print("  Headers:", headers[:9])

# Build UPC -> {cases, our_cost} map from Excel
xl_by_upc = {}
xl_no_upc = []
for row in rows[1:]:
    d = dict(zip(headers, row))
    upc_raw  = d.get("UPC")
    if isinstance(upc_raw, float): upc = str(int(upc_raw))
    elif upc_raw: upc = str(upc_raw).strip().split(".")[0]
    else: upc = ""
    brand    = str(d.get("Brand") or "").strip()
    desc     = str(d.get("Description") or "").strip()
    cases_raw, our_cost_raw = 0, 0
    for k, v in d.items():
        kl = k.lower()
        if "cases" in kl and "hand" in kl:
            cases_raw = v
        if "our" in kl and "cost" in kl:
            our_cost_raw = v
    try: cases = int(float(cases_raw)) if cases_raw else 0
    except (ValueError, TypeError): cases = 0
    try: our_cost = float(our_cost_raw) if our_cost_raw else 0.0
    except (ValueError, TypeError): our_cost = 0.0

    if upc and upc != "None":
        xl_by_upc[upc] = {"cases": cases, "our_cost": our_cost, "brand": brand, "desc": desc}
    elif brand or desc:
        xl_no_upc.append({"brand": brand, "desc": desc, "cases": cases, "our_cost": our_cost})

print(f"  {len(xl_by_upc)} rows with UPC, {len(xl_no_upc)} without UPC")


# ── 2. Load ERPNext items + barcodes ──────────────────────────────────────────
print("\n=== [2] Loading ERPNext items & barcodes ===")
erp_items = []
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item",
              params={"fields": '["name","item_name","brand","package_size","standard_rate"]',
                      "limit": 100, "limit_start": page * 100}, timeout=30)
    batch = r.json().get("data", [])
    if not batch: break
    erp_items.extend(batch)
    page += 1
print(f"  {len(erp_items)} items")

# Load barcodes from pre-fetched JSON (from tabItem Barcode via SSM)
import json as _json
with open("_barcodes.json") as f:
    _bc_data = _json.load(f)
item_barcodes = {}
for b in _bc_data:
    item_barcodes.setdefault(b["item_code"], []).append(str(b["barcode"]).strip())
print(f"  {len(_bc_data)} barcode records ({len(item_barcodes)} items with barcodes)")


# ── 3. Warehouse ──────────────────────────────────────────────────────────────
print("\n=== [3] Warehouse ===")
wh_r = s.get(f"{URL}/api/resource/Warehouse",
             params={"fields": '["name"]', "filters": '[["is_group","=",0]]', "limit": 10}, timeout=15)
default_wh = wh_r.json().get("data", [{}])[0].get("name", "Stores - AL")
print(f"  Using: {default_wh}")


# ── 4. Match by UPC ───────────────────────────────────────────────────────────
print("\n=== [4] Matching by UPC ===")
matched, unmatched = [], []
for item in erp_items:
    item_code = item["name"]
    codes = item_barcodes.get(item_code, [])
    xl = None
    for bc in codes:
        if bc in xl_by_upc:
            xl = xl_by_upc[bc]
            break
    if xl:
        matched.append((item, xl))
    else:
        unmatched.append(item)

print(f"  Matched  : {len(matched)}")
print(f"  Unmatched: {len(unmatched)}")
if unmatched[:5]:
    print("  Unmatched sample:")
    for u in unmatched[:5]:
        print(f"    {u['name']:14} {u.get('item_name','')[:40]}")


# ── 5. Delete any old draft reconciliation ────────────────────────────────────
old = s.get(f"{URL}/api/resource/Stock%20Reconciliation",
            params={"fields": '["name"]', "filters": '[["docstatus","=",0]]', "limit": 20}, timeout=15)
for doc in old.json().get("data", []):
    s.delete(f"{URL}/api/resource/Stock%20Reconciliation/{doc['name']}", timeout=15)
    print(f"  Deleted draft: {doc['name']}")


# ── 6. Build reconciliation items ─────────────────────────────────────────────
print("\n=== [6] Building items ===")
recon_items = []
for item, xl in matched:
    item_code  = item["name"]
    target_qty = xl["cases"]   # integer cases

    val_rate = xl["our_cost"]
    if val_rate <= 0:
        val_rate = float(item.get("standard_rate") or 0)
    if val_rate <= 0 and target_qty > 0:
        val_rate = 1.0

    recon_items.append({
        "doctype":        "Stock Reconciliation Item",
        "item_code":      item_code,
        "warehouse":      default_wh,
        "qty":            target_qty,
        "valuation_rate": round(val_rate, 4),
    })

print(f"  {len(recon_items)} items in reconciliation")
print("  Sample:")
for ri in recon_items[:8]:
    print(f"    {ri['item_code']:14} qty={ri['qty']:5}  val_rate={ri['valuation_rate']}")


# ── 7. Create + submit ────────────────────────────────────────────────────────
print("\n=== [7] Create & Submit ===")
r_create = s.post(f"{URL}/api/resource/Stock%20Reconciliation", json={
    "doctype":      "Stock Reconciliation",
    "purpose":      "Stock Reconciliation",
    "posting_date": "2026-06-26",
    "posting_time": "00:00:01",
    "company":      "Atlas Lakes",
    "items":        recon_items,
}, timeout=120)

if r_create.status_code not in (200, 201):
    print(f"Create FAILED {r_create.status_code}: {r_create.text[:300]}")
    exit(1)

recon_name = r_create.json()["data"]["name"]
print(f"  Created : {recon_name}")

r_sub = s.put(f"{URL}/api/resource/Stock%20Reconciliation/{recon_name}",
              json={"docstatus": 1}, timeout=120)

if r_sub.status_code in (200, 201):
    print(f"  Submitted: {recon_name} OK")
else:
    print(f"  Submit FAILED {r_sub.status_code}: {r_sub.text[:300]}")

print(f"""
=== Summary ===
Matched      : {len(matched)} / {len(erp_items)} items (by UPC)
Unmatched    : {len(unmatched)} items
Reconciliation: {recon_name}
Warehouse    : {default_wh}
""")
