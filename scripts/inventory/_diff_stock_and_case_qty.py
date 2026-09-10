import os
"""
Read-only diagnostic. Compares live ERPNext state (Bin stock + Item.items_per_case)
against data/Karavan Inventory-RECENT.csv, matched by UPC/barcode. Prints a diff.
Makes NO writes -- run this before any update script to see what would change.

Run:
    ERP_ADMIN_PWD=... python _diff_stock_and_case_qty.py
"""

import csv, requests
requests.packages.urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
CSV_PATH = "../../data/Karavan Inventory-RECENT.csv"

s = requests.Session(); s.verify = False
r = s.post(f"{URL}/api/method/login",
           data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"),
                 "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
print("Logged in\n")


# ── 1. Load CSV: UPC -> {cases, items_per_case} ────────────────────────────────
# NOTE: the sheet has UPCs reused across multiple package sizes of the same
# product (e.g. "Habash Whole Black Pepper" 6oz vs 25LB bulk both listed under
# 18227513821). A UPC that appears on >1 row is ambiguous -- we can't tell
# which ERP item it should match -- so those are dropped from the match set
# and reported separately rather than silently keeping just one row.
print("=== [1] Loading CSV ===")
csv_rows_by_upc = {}
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    headers = [h.replace("\n", " ").strip() for h in reader.fieldnames]
    reader.fieldnames = headers
    for row in reader:
        upc = (row.get("UPC") or "").strip()
        if not upc or upc.lower() == "none":
            continue
        cases_raw = row.get("Cases  On Hand") or row.get("Cases On Hand") or "0"
        ipc_raw = row.get("Items  Case/Unit") or row.get("Items Case/Unit") or ""
        try:
            cases = int(float(cases_raw)) if str(cases_raw).strip() else 0
        except ValueError:
            cases = 0
        try:
            ipc = int(float(ipc_raw)) if str(ipc_raw).strip() else None
        except ValueError:
            ipc = None
        csv_rows_by_upc.setdefault(upc, []).append({
            "cases": cases, "items_per_case": ipc,
            "brand": row.get("Brand", ""), "desc": row.get("Description", ""),
            "size": row.get("Size", "")})

ambiguous_upcs = {u: rows for u, rows in csv_rows_by_upc.items() if len(rows) > 1}
csv_by_upc = {u: rows[0] for u, rows in csv_rows_by_upc.items() if len(rows) == 1}
print(f"  {len(csv_by_upc)} unambiguous UPC rows loaded, {len(ambiguous_upcs)} UPCs skipped (reused across >1 row)")


# ── 2. Fetch live item names, then full docs (barcodes are a child table, ────────
#    not directly listable via REST -- "Item Barcode" list returns 403) ───────────
print("\n=== [2] Fetching live Items ===")
item_names = []
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item",
              params={"fields": '["name"]',
                      "limit": 200, "limit_start": page * 200}, timeout=30)
    batch = r.json().get("data", [])
    if not batch:
        break
    item_names.extend(x["name"] for x in batch)
    page += 1
print(f"  {len(item_names)} items")

print("\n=== [3] Fetching item docs (name, items_per_case, barcodes) ===")
erp_items = []
item_barcodes = {}
for i, name in enumerate(item_names):
    r = s.get(f"{URL}/api/resource/Item/{requests.utils.quote(name, safe='')}", timeout=30)
    d = r.json().get("data", {})
    erp_items.append({"name": d.get("name", name), "item_name": d.get("item_name", ""),
                       "items_per_case": d.get("items_per_case")})
    item_barcodes[name] = [str(b["barcode"]).strip() for b in d.get("barcodes", [])]
    if (i + 1) % 50 == 0:
        print(f"  {i + 1}/{len(item_names)}...")
print(f"  {len(erp_items)} item docs fetched")


# ── 4. Fetch live Bin stock (sum actual_qty per item) ────────────────────────────
print("\n=== [4] Fetching live Bin stock ===")
bins = []
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Bin",
              params={"fields": '["item_code","actual_qty"]',
                      "limit": 500, "limit_start": page * 500}, timeout=30)
    batch = r.json().get("data", [])
    if not batch:
        break
    bins.extend(batch)
    page += 1
stock_by_item = {}
for b in bins:
    stock_by_item[b["item_code"]] = stock_by_item.get(b["item_code"], 0) + (b.get("actual_qty") or 0)
print(f"  {len(bins)} bin rows ({len(stock_by_item)} items with stock)")


# ── 5. Match by UPC and diff ──────────────────────────────────────────────────────
print("\n=== [5] Matching & diffing ===")
stock_diffs, ipc_diffs, unmatched_erp, unmatched_csv = [], [], [], []
matched_upcs = set()

for item in erp_items:
    code = item["name"]
    codes = item_barcodes.get(code, [])
    csv_row = None
    for bc in codes:
        if bc in csv_by_upc:
            csv_row = csv_by_upc[bc]
            matched_upcs.add(bc)
            break
    if csv_row is None:
        unmatched_erp.append(code)
        continue

    live_stock = round(stock_by_item.get(code, 0))
    if live_stock != csv_row["cases"]:
        stock_diffs.append((code, item.get("item_name", ""), live_stock, csv_row["cases"]))

    live_ipc_raw = item.get("items_per_case")
    try:
        live_ipc = int(float(live_ipc_raw)) if str(live_ipc_raw or "").strip() else None
    except ValueError:
        live_ipc = live_ipc_raw
    if csv_row["items_per_case"] is not None and live_ipc != csv_row["items_per_case"]:
        ipc_diffs.append((code, item.get("item_name", ""), live_ipc, csv_row["items_per_case"]))

for upc, row in csv_by_upc.items():
    if upc not in matched_upcs:
        unmatched_csv.append((upc, row["brand"], row["desc"]))

print(f"\n  Stock diffs      : {len(stock_diffs)}")
print(f"  Items/case diffs : {len(ipc_diffs)}")
print(f"  ERP items w/o CSV UPC match : {len(unmatched_erp)}")
print(f"  CSV UPCs w/o ERP match      : {len(unmatched_csv)}")

if stock_diffs:
    print("\n--- Stock (cases on hand) diffs: item_code | name | live -> csv ---")
    for code, name, live, csv_v in stock_diffs[:400]:
        print(f"  {code:14} {name[:35]:35} {live:6} -> {csv_v:6}")

if ipc_diffs:
    print("\n--- Items per case diffs: item_code | name | live -> csv ---")
    for code, name, live, csv_v in ipc_diffs[:400]:
        print(f"  {code:14} {name[:35]:35} {str(live):6} -> {str(csv_v):6}")

if unmatched_csv:
    print("\n--- CSV rows with no ERP UPC match (sample) ---")
    for upc, brand, desc in unmatched_csv[:30]:
        print(f"  {upc:16} {brand[:20]:20} {desc[:35]}")

if ambiguous_upcs:
    print(f"\n--- Ambiguous UPCs skipped ({len(ambiguous_upcs)} UPC(s) shared by >1 CSV row) ---")
    for upc, rows in ambiguous_upcs.items():
        print(f"  UPC {upc}:")
        for row in rows:
            print(f"    {row['brand'][:20]:20} {row['desc'][:35]:35} size={row['size']:10} "
                  f"cases={row['cases']} items/case={row['items_per_case']}")

print("\nDone. No writes performed.")
