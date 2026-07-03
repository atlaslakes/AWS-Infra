"""
Find UPCs for items in items_missing_price.csv from:
  1. Data_06_23.csv (Toast POS)
  2. Karavan Inventory-updated.xlsx
Then update the CSV and push UPCs to ERPNext custom_barcode field.
"""

import csv, re, openpyxl, requests
from difflib import SequenceMatcher
requests.packages.urllib3.disable_warnings()

# ── helpers ───────────────────────────────────────────────────────────────────
def norm(v):
    if not v: return ""
    v = str(v).lower().strip()
    v = re.sub(r"[^\w\s]", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()

def to_base(value, unit):
    unit = str(unit).lower().strip()
    conv = {"g":1,"gr":1,"gram":1,"grams":1,"kg":1000,"oz":28.3495,"oz.":28.3495,
            "lb":453.592,"lbs":453.592,"ml":1,"l":1000}
    return value * conv.get(unit, 0) if unit in conv else None

SIZE_RE = re.compile(r"([\d.]+)\s*([a-z]+)", re.I)

def parse_size(v):
    m = SIZE_RE.match(str(v or "").strip())
    if not m: return None
    try:
        return to_base(float(m.group(1)), m.group(2))
    except ValueError:
        return None

def sizes_match(a, b, tol=0.08):
    if norm(a) == norm(b): return True
    ga, gb = parse_size(a), parse_size(b)
    if ga and gb and max(ga, gb) > 0:
        return abs(ga - gb) / max(ga, gb) <= tol
    return False

# ── 1. Load missing items ─────────────────────────────────────────────────────
missing = []
with open(r"c:\Users\aizen\Desktop\AWS\data\items_missing_price.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        missing.append(dict(row))
print(f"Missing items: {len(missing)}")

# ── 2. Load Toast CSV ─────────────────────────────────────────────────────────
toast = []
with open("data/Data_06_23.csv", newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        upc = (row.get("UPCcode") or row.get("TOAST_UPCCODE") or "").strip()
        if upc and upc not in ("0", ""):
            toast.append({
                "upc":   upc,
                "brand": (row.get("Branddescription") or "").strip(),
                "name":  (row.get("Expandeddescription") or row.get("POSdescription") or "").strip(),
                "size":  (row.get("Sizedescription") or "").strip(),
                "price": (row.get("Activeprice") or "").strip(),
            })
print(f"Toast rows with UPC: {len(toast)}")

# ── 3. Load Excel ─────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx",
                             read_only=True, data_only=True)
ws = wb.active
xl_rows = list(ws.iter_rows(values_only=True))
xl_headers = [str(h).replace("\n", " ").strip() if h else "" for h in xl_rows[0]]
xl_items = []
for row in xl_rows[1:]:
    d = dict(zip(xl_headers, row))
    upc = str(d.get("UPC") or "").strip().split(".")[0]
    if upc and upc not in ("0", "", "None"):
        xl_items.append({
            "upc":   upc,
            "brand": str(d.get("Brand") or "").strip(),
            "name":  str(d.get("Description") or "").strip(),
            "size":  str(d.get("Size") or "").strip(),
        })
print(f"Excel rows with UPC: {len(xl_items)}\n")

# ── 4. Match each missing item ────────────────────────────────────────────────
def find_upc(item_name, brand, size):
    best_upc, best_score, best_src = None, 0, None

    for source, rows in [("Toast", toast), ("Excel", xl_items)]:
        for t in rows:
            if brand:
                b_sim = sim(brand, t["brand"])
                brand_in = norm(brand) in norm(t["brand"]) or norm(t["brand"]) in norm(brand)
                if b_sim < 0.7 and not brand_in:
                    continue
            score = sim(item_name, t["name"])
            if size and t.get("size") and not sizes_match(size, t["size"]):
                score *= 0.5
            if score > best_score:
                best_score, best_upc, best_src = score, t["upc"], source

    return (best_upc, best_src, best_score) if best_score >= 0.45 else (None, None, 0)

found, not_found = 0, 0
for item in missing:
    if item.get("upc_barcode", "").strip():
        found += 1
        print(f"  HAS    {item['item_code']:12} {item['item_name'][:40]:40} UPC={item['upc_barcode']}")
        continue
    upc, src, score = find_upc(item["item_name"], item.get("brand",""), item.get("size",""))
    if upc:
        item["upc_barcode"] = upc
        found += 1
        print(f"  FOUND  {item['item_code']:12} {item['item_name'][:40]:40} UPC={upc} via {src} ({score:.2f})")
    else:
        not_found += 1
        print(f"  MISS   {item['item_code']:12} {item['item_name'][:40]:40}")

print(f"\nFound: {found}  Not found: {not_found}")

# ── 5. Write updated CSV ──────────────────────────────────────────────────────
out_path = r"c:\Users\aizen\Desktop\AWS\data\items_missing_price_updated.csv"
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in missing:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
print(f"Written to {out_path}")

# ── 6. Push UPCs to ERPNext ───────────────────────────────────────────────────
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": "TempMigrate2026!"}, timeout=15)

updated_erp, skipped_erp = 0, 0
for item in missing:
    upc = item.get("upc_barcode", "").strip()
    code = item.get("item_code", "").strip()
    if not upc or not code:
        skipped_erp += 1
        continue
    r = s.post(f"{URL}/api/method/frappe.client.set_value",
               json={"doctype": "Item", "name": code,
                     "fieldname": "custom_barcode", "value": upc}, timeout=15)
    if r.status_code in (200, 201):
        updated_erp += 1
    else:
        print(f"  ERR {code}: {r.text[:80]}")
        skipped_erp += 1

print(f"ERPNext updated: {updated_erp} items, skipped: {skipped_erp}")
