import os
"""
Loads opening stock into ERPNext from:
  aws-infra/Karavan Inventory - Sheet1.csv

Steps:
  1. Build UPC -> item_code lookup from tabItem Barcode
  2. Match CSV rows by UPC
  3. Create + submit a Stock Reconciliation (purpose: Opening Stock)

After this, the Inventory Manager report will show live quantities,
and every submitted Sales Invoice (Update Stock = On) will auto-deduct.
"""
import requests, csv, json, datetime

CSV_PATH  = r"C:\Users\aizen\Desktop\AWS\aws-infra\Karavan Inventory - Sheet1.csv"
WAREHOUSE = "Stores - AL"
URL       = "https://www.karavanimports.com"
PASS      = os.environ.get("ERP_ADMIN_PWD")

requests.packages.urllib3.disable_warnings()
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=20)
print("Logged in\n")

# ── 1. Company name ────────────────────────────────────────────────────────────
company = s.get(f"{URL}/api/resource/Company",
                params={"fields": '["name"]', "limit": 1}, timeout=20
                ).json()["data"][0]["name"]
print(f"Company: {company}")

# ── 2. Build name-based lookup + save barcodes while we're at it ───────────────
print("\n[1] Fetching items from ERPNext...")
items_resp = s.get(f"{URL}/api/resource/Item",
                   params={"fields": '["name","item_name","brand"]', "limit": 500},
                   timeout=30).json().get("data", [])
print(f"  {len(items_resp)} items loaded")

def norm(t):
    return " ".join(str(t).lower().split())

# primary: exact item_name match
name_map = {norm(i["item_name"]): i["name"] for i in items_resp}
# secondary: brand + item_name (some items store only desc in item_name)
brand_name_map = {norm((i.get("brand") or "") + " " + i["item_name"]): i["name"]
                  for i in items_resp}

# ── 3. Read CSV and match ──────────────────────────────────────────────────────
print("\n[2] Reading CSV and matching to ERPNext items...")
qty_accum   = {}   # item_code -> total qty (sum across CSV rows)
upc_accum   = {}   # item_code -> first UPC seen
unmatched   = []

with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        upc      = str(row.get("UPC", "")).strip()
        brand    = str(row.get("Brand", "")).strip().rstrip()
        desc     = str(row.get("Description", "")).strip()
        qty_raw  = str(row.get("Cases On Hand", "0")).strip()

        try:
            qty = float(qty_raw) if qty_raw else 0.0
        except ValueError:
            qty = 0.0

        if qty <= 0:
            continue

        full_name = norm(brand + " " + desc)
        desc_only = norm(desc)

        item_code = (name_map.get(full_name) or
                     brand_name_map.get(full_name) or
                     name_map.get(desc_only))

        if not item_code:
            unmatched.append({"upc": upc, "brand": brand, "desc": desc, "qty": qty})
            continue

        qty_accum[item_code] = qty_accum.get(item_code, 0) + qty
        if upc and item_code not in upc_accum:
            upc_accum[item_code] = upc
        print(f"  MATCH  {item_code:12s}  {brand} {desc[:35]:35s}  qty={qty}")

# Build deduplicated recon list
recon_items = [
    {"item_code": code, "warehouse": WAREHOUSE, "qty": total_qty, "valuation_rate": 1.0}
    for code, total_qty in qty_accum.items()
]
barcode_updates = list(upc_accum.items())  # (item_code, upc)

print(f"\n  Matched:   {len(recon_items)}")
print(f"  Unmatched: {len(unmatched)}")
if unmatched:
    print("\n  --- Unmatched ---")
    for u in unmatched:
        print(f"  {u['brand']} {u['desc']}  (UPC={u['upc'] or 'none'})  qty={u['qty']}")

# ── 2b. Save barcodes back to Item Barcode so future UPC lookups work ──────────
if barcode_updates:
    print(f"\n[2b] Saving {len(barcode_updates)} barcodes to Item master...")
    ok = 0
    for item_code, upc in barcode_updates:
        rb = s.put(f"{URL}/api/resource/Item/{requests.utils.quote(item_code, safe='')}",
                   json={"barcodes": [{"barcode": upc, "barcode_type": ""}]}, timeout=20)
        if rb.status_code == 200:
            ok += 1
        else:
            print(f"  barcode ERR {item_code}: {rb.status_code}")
    print(f"  {ok} barcodes saved")

if not recon_items:
    print("\nNothing to reconcile. Exiting.")
    raise SystemExit(0)

# ── 4. Create Stock Reconciliation ─────────────────────────────────────────────
print(f"\n[3] Creating Stock Reconciliation ({len(recon_items)} items)...")
today = datetime.date.today().strftime("%Y-%m-%d")

payload = {
    "doctype":       "Stock Reconciliation",
    "company":       company,
    "posting_date":  today,
    "posting_time":  "08:00:00",
    "purpose":       "Stock Reconciliation",
    "items":         recon_items,
}
r = s.post(f"{URL}/api/resource/Stock%20Reconciliation", json=payload, timeout=60)
if r.status_code not in (200, 201):
    print(f"  CREATE FAILED {r.status_code}: {r.text[:400]}")
    raise SystemExit(1)

doc_name = r.json()["data"]["name"]
print(f"  Created: {doc_name}")

# ── 5. Submit ──────────────────────────────────────────────────────────────────
print("\n[4] Submitting...")
rs = s.put(f"{URL}/api/resource/Stock%20Reconciliation/{requests.utils.quote(doc_name, safe='')}",
           json={"docstatus": 1}, timeout=60)
if rs.status_code == 200:
    print(f"  Submitted OK — {doc_name}")
    print("\nDone. Open Stock > Inventory Manager to verify quantities.")
else:
    print(f"  SUBMIT FAILED {rs.status_code}: {rs.text[:400]}")
    print(f"  Document saved as draft: {doc_name}")
    print("  Submit manually via Stock > Stock Reconciliation > {doc_name}")
