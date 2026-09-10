"""Push the UPCs found from matching run directly to ERPNext and update CSV."""
import csv, requests, os
requests.packages.urllib3.disable_warnings()

# UPCs confirmed from matching run (81 found, 2 missed)
UPCS = {
    "GEN-0084":   "0000000054545",
    "COND-0011":  "0081007098303",
    "SPICE-0025": "0004133103776",
    "BEAN-0042":  "6222001002973",
    "GRAIN-0004": "896600002908",
    "GRAIN-0005": "6223000660027",
    "OIL-0002":   "6251080000136",
    "OIL-0003":   "6251080000211",
    "OIL-0001":   "6251080051039",
    "SPICE-0001": "0069255100002",
    "PICKLE-0003":"0625380945001",
    "SPICE-0003": "0020600300000",
    "PICKLE-0013":"850051813155",
    "SNACK-0001": "6191402804632",
    "OIL-0005":   "6253807320107",
    "SPICE-0006": "822514325109",
    "BEV-0009":   "0020400500000",
    "SPICE-0008": "18436000236528",
    "NUT-0002":   "10074265020544",
    "NUT-0001":   "10074265017001",
    "SNACK-0004": "9501100018595",
    "SNACK-0003": "9501100019639",
    "SNACK-0002": "9501100019769",
    "SPICE-0009": "682863057171",
    "COND-0006":  "400015199094",
    "BEV-0010":   "47960627554096",
    "BEAN-0032":  "6251136051204",
    "BEV-0011":   "762571312080",
    "BEV-0013":   "0076257131203",
    "BEV-0012":   "762571312158",
    "SPICE-0010": "762571312103",
    "BEV-0014":   "762571312219",
    "BEAN-0034":  "19175062003",
    "COND-0007":  "77391128002",
    "PICKLE-0036":"19175057412",
    "SPICE-0016": "18227513395",
    "SPICE-0012": "0020500800000",
    "SPICE-0017": "18227513692",
    "GEN-0018":   "0001822751394",
    "COND-0008":  "6731439455393",
    "GEN-0025":   "0000000070007",
    "GEN-0024":   "18227513821",
    "GEN-0026":   "10074265014048",
    "BEV-0016":   "850075808519",
    "DAIRY-0001": "850075808496",
    "GEN-0029":   "8994963002008",
    "GEN-0034":   "850083598020",
    "GEN-0037":   "48001016460",
    "GEN-0039":   "850075808571",
    "GEN-0040":   "28000088057",
    "NUT-0008":   "899177000377",
    "PICKLE-0044":"703669331323",
    "SNACK-0007": "9501100019370",
    "BEAN-0038":  "6253001321023",
    "GEN-0050":   "6253001321726",
    "SPICE-0029": "0063923510752",
    "SPICE-0032": "0063923510713",
    "SPICE-0026": "0063923510720",
    "SPICE-0028": "0063923510727",
    "SPICE-0027": "0063923510742",
    "SPICE-0030": "0063923510714",
    "SPICE-0033": "0890800033985",
    "SPICE-0031": "0063923510714",
    "GEN-0062":   "6267598",
    "GEN-0064":   "6251041220078",
    "GEN-0065":   "6251041220030",
    "GEN-0063":   "6251041220047",
    "GEN-0066":   "18801073123622",
    "PASTA-0008": "0008516412030",
    "BEV-0029":   "54023888",
    "BEAN-0040":  "0000000050006",
    "SNACK-0011": "9501100018342",
    "PICKLE-0046":"74265023357",
    "GEN-0072":   "10074265002533",
    "PICKLE-0047":"760695003020",
    "GEN-0073":   "8500459277760",
    "BEV-0034":   "6223000274491",
    "SNACK-0012": "8693029911161",
    "GEN-0074":   "90010212A30925",
    "GEN-0082":   "10074265003019",
}

# ── 1. Update ERPNext ─────────────────────────────────────────────────────────
URL = "https://erpnext.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": "TempMigrate2026!"}, timeout=15)
print("Logged in")

ok, fail = 0, 0
for code, upc in UPCS.items():
    # strip leading * if present (from Excel annotation)
    upc = upc.lstrip("*").strip()
    r = s.post(f"{URL}/api/method/frappe.client.set_value",
               json={"doctype": "Item", "name": code,
                     "fieldname": "custom_barcode", "value": upc}, timeout=15)
    if r.status_code in (200, 201):
        ok += 1
    else:
        print(f"  FAIL {code}: {r.text[:80]}")
        fail += 1

print(f"ERPNext: {ok} updated, {fail} failed")

# ── 2. Update the CSV ─────────────────────────────────────────────────────────
csv_path = r"c:\Users\aizen\Desktop\AWS\data\items_missing_price.csv"
out_path = r"c:\Users\aizen\Desktop\AWS\data\items_missing_price_updated.csv"

rows = []
with open(csv_path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        code = row.get("item_code", "").strip()
        if code in UPCS and not row.get("upc_barcode", "").strip():
            row["upc_barcode"] = UPCS[code].lstrip("*").strip()
        rows.append(row)

with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"CSV written to: {out_path}")
print(f"\nNot found (no UPC): SPICE-0011 (Habash Shawarma Beef Spices), NUT-0012 (TRC Golden Raisins)")
