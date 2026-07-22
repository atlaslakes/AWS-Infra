import os
"""
Applies the diffs found by _diff_stock_and_case_qty.py:
  1. Updates Item.items_per_case for items where it differs from
     data/Karavan Inventory-RECENT.csv (matched by UPC).
  2. Creates + submits one Stock Reconciliation that sets Bin.actual_qty
     ("cases on hand") to match the CSV, preserving each item's existing
     valuation_rate (so the cost-sync scheduled job isn't disturbed).

Ambiguous UPCs (same UPC on >1 CSV row -- different package sizes of the
same product) are skipped, same as the diff script.

Run:
    ERP_ADMIN_PWD=... python _apply_stock_and_case_qty.py
"""

import csv, requests
requests.packages.urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
CSV_PATH = "../../data/Karavan Inventory-RECENT.csv"

s = requests.Session(); s.verify = False
r = s.post(f"{URL}/api/method/login",
           data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"),
                 "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
print("Logged in\n")


# ── 1. Load CSV (unambiguous UPCs only) ─────────────────────────────────────────
print("=== [1] Loading CSV ===")
csv_rows_by_upc = {}
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    reader.fieldnames = [h.replace("\n", " ").strip() for h in reader.fieldnames]
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
        csv_rows_by_upc.setdefault(upc, []).append({"cases": cases, "items_per_case": ipc})

csv_by_upc = {u: rows[0] for u, rows in csv_rows_by_upc.items() if len(rows) == 1}
print(f"  {len(csv_by_upc)} unambiguous UPC rows "
      f"({len(csv_rows_by_upc) - len(csv_by_upc)} ambiguous UPCs skipped)")


# ── 2. Fetch live items (name, items_per_case, barcodes) ───────────────────────
print("\n=== [2] Fetching live items ===")
item_names = []
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item",
              params={"fields": '["name"]', "limit": 200, "limit_start": page * 200}, timeout=30)
    batch = r.json().get("data", [])
    if not batch:
        break
    item_names.extend(x["name"] for x in batch)
    page += 1

erp_items = []
for i, name in enumerate(item_names):
    r = s.get(f"{URL}/api/resource/Item/{requests.utils.quote(name, safe='')}", timeout=30)
    d = r.json().get("data", {})
    erp_items.append({
        "name": d.get("name", name),
        "items_per_case": d.get("items_per_case"),
        "disabled": d.get("disabled"),
        "barcodes": [str(b["barcode"]).strip() for b in d.get("barcodes", [])],
    })
    if (i + 1) % 100 == 0:
        print(f"  {i + 1}/{len(item_names)}...")
print(f"  {len(erp_items)} items fetched")


# ── 3. Fetch live Bin (qty + valuation_rate, single warehouse "Stores - AL") ───
print("\n=== [3] Fetching live Bin ===")
bins = []
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Bin",
              params={"fields": '["item_code","warehouse","actual_qty","valuation_rate"]',
                      "limit": 500, "limit_start": page * 500}, timeout=30)
    batch = r.json().get("data", [])
    if not batch:
        break
    bins.extend(batch)
    page += 1
bin_by_item = {b["item_code"]: b for b in bins}
print(f"  {len(bins)} bin rows")


# ── 4. Match by UPC, build diffs ────────────────────────────────────────────────
print("\n=== [4] Matching ===")
stock_updates, ipc_updates, skipped_disabled = [], [], []
for item in erp_items:
    code = item["name"]
    csv_row = None
    for bc in item["barcodes"]:
        if bc in csv_by_upc:
            csv_row = csv_by_upc[bc]
            break
    if csv_row is None:
        continue

    live_bin = bin_by_item.get(code)
    live_stock = round(live_bin["actual_qty"]) if live_bin else 0
    if live_stock != csv_row["cases"]:
        if item.get("disabled"):
            skipped_disabled.append(code)
        else:
            val_rate = round(float(live_bin["valuation_rate"]), 4) if live_bin and live_bin.get("valuation_rate") else 0
            if val_rate <= 0 and csv_row["cases"] > 0:
                val_rate = 1.0  # ERPNext requires a positive valuation_rate for a qty>0 row with no prior stock
            stock_updates.append({"item_code": code, "qty": csv_row["cases"], "valuation_rate": val_rate})

    live_ipc_raw = item.get("items_per_case")
    try:
        live_ipc = int(float(live_ipc_raw)) if str(live_ipc_raw or "").strip() else None
    except ValueError:
        live_ipc = live_ipc_raw
    if csv_row["items_per_case"] is not None and live_ipc != csv_row["items_per_case"]:
        ipc_updates.append({"item_code": code, "items_per_case": csv_row["items_per_case"]})

print(f"  Stock updates: {len(stock_updates)}")
print(f"  Items/case updates: {len(ipc_updates)}")
if skipped_disabled:
    print(f"  Skipped (disabled item, no stock update): {skipped_disabled}")


# ── 5. Apply items_per_case updates ─────────────────────────────────────────────
print("\n=== [5] Updating items_per_case ===")
for upd in ipc_updates:
    r = s.post(f"{URL}/api/method/frappe.client.set_value",
               json={"doctype": "Item", "name": upd["item_code"],
                     "fieldname": "items_per_case", "value": upd["items_per_case"]}, timeout=15)
    status = "OK" if r.status_code in (200, 201) else f"FAIL {r.status_code} {r.text[:100]}"
    print(f"  {upd['item_code']:14} -> items_per_case={upd['items_per_case']}  {status}")


# ── 6. Apply stock updates via Stock Reconciliation ─────────────────────────────
print("\n=== [6] Stock Reconciliation ===")
if not stock_updates:
    print("  Nothing to reconcile.")
else:
    old = s.get(f"{URL}/api/resource/Stock%20Reconciliation",
                params={"fields": '["name"]', "filters": '[["docstatus","=",0]]', "limit": 20}, timeout=15)
    for doc in old.json().get("data", []):
        s.delete(f"{URL}/api/resource/Stock%20Reconciliation/{doc['name']}", timeout=15)
        print(f"  Deleted stale draft: {doc['name']}")

    recon_items = [{
        "doctype": "Stock Reconciliation Item",
        "item_code": u["item_code"],
        "warehouse": "Stores - AL",
        "qty": u["qty"],
        "valuation_rate": u["valuation_rate"],
    } for u in stock_updates]

    r_create = s.post(f"{URL}/api/resource/Stock%20Reconciliation", json={
        "doctype": "Stock Reconciliation",
        "purpose": "Stock Reconciliation",
        "company": "Atlas Lakes",
        "items": recon_items,
    }, timeout=120)

    if r_create.status_code not in (200, 201):
        print(f"  Create FAILED {r_create.status_code}: {r_create.text[:400]}")
    else:
        recon_name = r_create.json()["data"]["name"]
        print(f"  Created: {recon_name}")
        r_sub = s.put(f"{URL}/api/resource/Stock%20Reconciliation/{recon_name}",
                      json={"docstatus": 1}, timeout=120)
        if r_sub.status_code in (200, 201):
            print(f"  Submitted: {recon_name} OK")
        else:
            print(f"  Submit FAILED {r_sub.status_code}: {r_sub.text[:400]}")

print("\nDone.")
