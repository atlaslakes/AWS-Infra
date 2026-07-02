import os, requests, csv
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# ── Pull live ERPNext inventory ────────────────────────────────────────────────
r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
erp_rows = [x for x in r.json().get("message", {}).get("result", []) if isinstance(x, dict)]

# Show actual keys from first row so we can debug
if erp_rows:
    print("ERP row keys:", list(erp_rows[0].keys()))

# Index by UPC and by item_id
erp_by_upc  = {}
erp_by_name = {}
UPC_KEY = None
for key in (erp_rows[0].keys() if erp_rows else []):
    if "upc" in key.lower() or "barcode" in key.lower():
        UPC_KEY = key
        break
print("UPC key detected:", UPC_KEY)

for row in erp_rows:
    upc = str(row.get(UPC_KEY) or "").strip()
    if upc:
        erp_by_upc.setdefault(upc, []).append(row)
    erp_by_name[row.get("description", "").strip().lower()] = row

# ── Read CSV ───────────────────────────────────────────────────────────────────
csv_rows = []
with open("Karavan Inventory - Sheet1.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            qty = float(str(row.get("Cases On Hand", "0") or "0").strip())
        except ValueError:
            qty = 0
        csv_rows.append({
            "brand":       row.get("Brand", "").strip(),
            "description": row.get("Description", "").strip(),
            "upc":         str(row.get("UPC", "") or "").strip(),
            "csv_qty":     qty,
        })

# ── Compare ────────────────────────────────────────────────────────────────────
matched   = []
no_match  = []

for c in csv_rows:
    erp = None
    # 1. Match by UPC
    if c["upc"] and c["upc"] in erp_by_upc and erp_by_upc[c["upc"]]:
        candidates = erp_by_upc[c["upc"]]
        # pick the one whose description is closest
        if len(candidates) == 1:
            erp = candidates[0]
        else:
            desc_lower = c["description"].lower()
            erp = min(candidates, key=lambda x: len(set(x.get("description","").lower().split()) ^ set(desc_lower.split())))
    # 2. Fallback: description match
    if not erp:
        key = c["description"].lower()
        erp = erp_by_name.get(key)

    if erp:
        erp_qty = erp.get("cases_on_hand") or 0
        matched.append({
            "item_id":   erp.get("item_id"),
            "desc":      c["description"],
            "upc":       c["upc"],
            "csv_qty":   c["csv_qty"],
            "erp_qty":   erp_qty,
            "diff":      c["csv_qty"] - erp_qty,
        })
    else:
        no_match.append(c)

# ── Report ─────────────────────────────────────────────────────────────────────
needs_update = [m for m in matched if m["diff"] != 0]
in_sync      = [m for m in matched if m["diff"] == 0]

print(f"Total CSV rows:    {len(csv_rows)}")
print(f"Matched to ERP:    {len(matched)}")
print(f"In sync:           {len(in_sync)}")
print(f"Need update:       {len(needs_update)}")
print(f"No ERP match:      {len(no_match)}")

print(f"\n{'ITEM':<14} {'DESCRIPTION':<45} {'CSV':>6} {'ERP':>6} {'DIFF':>6}")
print("-"*80)
for m in sorted(needs_update, key=lambda x: abs(x["diff"]), reverse=True):
    flag = "+" if m["diff"] > 0 else "-"
    print(f"{m['item_id'] or '':14} {m['desc'][:44]:<45} {m['csv_qty']:>6.1f} {m['erp_qty']:>6.1f} {m['diff']:>+6.1f} {flag}")

if no_match:
    print(f"\nCSV rows with no ERP match ({len(no_match)}):")
    for n in no_match:
        print(f"  [{n['upc'] or 'no UPC':15}] {n['brand']} - {n['description']} (qty={n['csv_qty']})")
