import os
"""Push handwritten prices transcribed from data/Scan_20260708.pdf and
data/Scan_20260708 (2).pdf to ERPNext, and update the local CSV.

Writes to the cost/margin/selling-price model set up by
scripts/inventory/setup_cost_margin_pricing.py: sets Item.valuation_rate
(cost) and Bin.valuation_rate for any existing stock, then re-derives
Item Price (Standard Selling) from that item's "Margin - <item_code>"
Pricing Rule -- no more direct writes to standard_rate/custom_price.

Items with no handwritten price are left untouched (still NO PRICE).

Run:
    ERP_ADMIN_USR=... ERP_ADMIN_PWD=... python _push_scanned_prices.py
"""
import csv
import sys
import requests

requests.packages.urllib3.disable_warnings()

# item_code -> price read from the scanned sheets (61 of 83 had a handwritten price)
PRICES = {
    "GEN-0084": 74.99, "COND-0011": 16.99, "SPICE-0025": 64.00,
    "GRAIN-0004": 48.00, "GRAIN-0005": 54.00, "OIL-0002": 148.00,
    "OIL-0003": 85.00, "OIL-0001": 101.00, "SPICE-0001": 92.00,
    "PICKLE-0003": 37.00, "SNACK-0001": 50.00, "OIL-0005": 50.00,
    "OIL-0006": 46.00, "SPICE-0006": 36.00, "BEV-0009": 87.00,
    "NUT-0002": 35.00, "NUT-0001": 58.00, "SNACK-0004": 16.98,
    "SNACK-0003": 20.29, "SNACK-0002": 20.00, "BEV-0010": 82.00,
    "BEAN-0032": 94.00, "BEV-0011": 31.00, "BEV-0013": 31.00,
    "BEV-0012": 31.00, "SPICE-0010": 31.00, "BEV-0014": 31.00,
    "BEAN-0034": 50.00, "SPICE-0016": 128.00, "SPICE-0012": 184.00,
    "SPICE-0017": 178.00, "GEN-0018": 19.88, "SPICE-0011": 124.00,
    "GEN-0025": 124.00, "GEN-0024": 153.00, "GEN-0026": 72.00,
    "BEV-0016": 42.00, "DAIRY-0001": 42.00, "GEN-0029": 14.00,
    "GEN-0034": 36.00, "GEN-0039": 53.00, "GEN-0040": 135.00,
    "PICKLE-0044": 131.00, "BEAN-0038": 33.00, "SPICE-0029": 30.00,
    "SPICE-0032": 39.99, "SPICE-0026": 49.99, "SPICE-0028": 39.99,
    "SPICE-0027": 30.00, "SPICE-0030": 30.00, "SPICE-0033": 34.99,
    "SPICE-0031": 32.00, "GEN-0062": 15.99, "GEN-0064": 33.00,
    "GEN-0065": 39.99, "GEN-0063": 33.00, "GEN-0066": 50.00,
    "PASTA-0008": 27.99, "BEV-0029": 20.00,
    "SNACK-0011": 20.00, "PICKLE-0046": 32.00, "GEN-0072": 32.00,
    "GEN-0073": 33.00, "BEV-0034": 54.99, "SNACK-0012": 23.99,
    "GEN-0082": 43.00,
}

URL = "https://www.karavanimports.com"
s = requests.Session()
s.verify = False
login_resp = s.post(f"{URL}/api/method/login",
                     data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"),
                           "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
if login_resp.status_code != 200:
    print(f"Login failed {login_resp.status_code}: {login_resp.text[:300]}")
    sys.exit(1)
print("Logged in")

ok, fail = 0, 0
for code, cost in PRICES.items():
    r = s.post(f"{URL}/api/method/frappe.client.set_value",
               json={"doctype": "Item", "name": code, "fieldname": "valuation_rate", "value": cost},
               timeout=15)
    if r.status_code not in (200, 201):
        print(f"  FAIL {code} (cost): {r.text[:150]}")
        fail += 1
        continue

    margin_row = s.get(f"{URL}/api/resource/Pricing Rule",
                        params={"filters": f'[["title","=","Margin - {code}"]]',
                                "fields": '["margin_type","margin_rate_or_amount"]'}, timeout=15)
    rule = (margin_row.json().get("data") or [{}])[0]
    margin_type = rule.get("margin_type") or "Percentage"
    margin = rule.get("margin_rate_or_amount") or 0
    new_price = cost * (1 + margin / 100) if margin_type == "Percentage" else cost + margin

    existing = s.get(f"{URL}/api/resource/Item Price",
                      params={"filters": f'[["item_code","=","{code}"],["price_list","=","Standard Selling"]]',
                              "fields": '["name"]'}, timeout=15)
    rows = existing.json().get("data", [])
    if rows:
        r2 = s.put(f"{URL}/api/resource/Item Price/{rows[0]['name']}",
                    json={"price_list_rate": new_price}, timeout=15)
    else:
        r2 = s.post(f"{URL}/api/resource/Item Price",
                     json={"item_code": code, "price_list": "Standard Selling",
                           "selling": 1, "price_list_rate": new_price}, timeout=15)
    if r2.status_code in (200, 201):
        ok += 1
    else:
        print(f"  FAIL {code} (price): {r2.text[:150]}")
        fail += 1

print(f"ERPNext: {ok} updated, {fail} failed")

# ── Update the CSV ──────────────────────────────────────────────────────────
csv_path = r"c:\Users\aizen\Desktop\AWS\data\items_missing_price.csv"
out_path = r"c:\Users\aizen\Desktop\AWS\data\items_missing_price_updated.csv"

rows = []
with open(csv_path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        code = row.get("item_code", "").strip()
        if code in PRICES:
            row["standard_price"] = f"{PRICES[code]:.2f}"
            row["price_status"] = "PRICED"
        rows.append(row)

with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"CSV written to: {out_path}")
print(f"Still NO PRICE (blank on scan): {sum(1 for r in rows if r.get('price_status') == 'NO PRICE')}")
