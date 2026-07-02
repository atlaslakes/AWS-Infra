import os
import requests, csv, re
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# 1. Check set_value error for BEV-0007
print("=== set_value error for BEV-0007 ===")
r = s.post(f"{URL}/api/method/frappe.client.set_value",
           data={"doctype": "Item", "name": "BEV-0007",
                 "fieldname": "standard_rate", "value": "3.99"}, timeout=15)
print(f"Status: {r.status_code}")
try:
    d = r.json()
    print("Exception:", d.get("exception", "")[:300])
    print("Message:", str(d.get("message", ""))[:200])
    print("Server msg:", str(d.get("_server_messages", ""))[:200])
except:
    print(r.text[:300])

# Try custom_price only
print("\n=== set_value custom_price for BEV-0007 ===")
r2 = s.post(f"{URL}/api/method/frappe.client.set_value",
            data={"doctype": "Item", "name": "BEV-0007",
                  "fieldname": "custom_price", "value": "3.99"}, timeout=15)
print(f"Status: {r2.status_code}")

# 2. Check unmatched brand variants
print("\n=== CSV brand survey for unmatched brands ===")
brands_in_csv = set()
with open("Data_06_23.csv", encoding="utf-8", errors="replace") as f:
    for row in csv.DictReader(f):
        b = (row.get("Branddescription") or "").strip()
        if b:
            brands_in_csv.add(b)

# Look for brands similar to unmatched ERPNext brands
unmatched_brands = [
    "Ziyad Brand", "AlGhazal", "AlDayaa", "AlKhityar", "AlWalimah",
    "Al Afia", "Al Hor", "Durra", "Sahtein", "Sultan", "Golden",
    "Golden Brand", "Golden Harvest", "Al Doha", "Shahia", "Ahmad Tea London",
    "Habash", "Castania", "Best Choice", "Indomie", "Samyang"
]

for erp_brand in unmatched_brands:
    matches = [b for b in brands_in_csv
               if erp_brand.lower() in b.lower() or b.lower() in erp_brand.lower()
               or any(w in b.lower() for w in erp_brand.lower().split())]
    if matches:
        print(f"  ERPNext: '{erp_brand}'  ->  CSV: {matches[:5]}")
    else:
        print(f"  ERPNext: '{erp_brand}'  ->  NOT FOUND in CSV")

# 3. Check Ziyad in CSV specifically
print("\n=== Ziyad items in CSV ===")
with open("Data_06_23.csv", encoding="utf-8", errors="replace") as f:
    for row in csv.DictReader(f):
        b = (row.get("Branddescription") or "").strip()
        if "ziyad" in b.lower():
            size = row.get("Sizedescription", "")
            expanded = row.get("Expandeddescription", "")
            price = row.get("Activeprice") or row.get("Price") or ""
            print(f"  {b} | {size} | {expanded} | ${price}")

# 4. Check Durra items in CSV
print("\n=== Durra items in CSV ===")
with open("Data_06_23.csv", encoding="utf-8", errors="replace") as f:
    for row in csv.DictReader(f):
        b = (row.get("Branddescription") or "").strip()
        if "durra" in b.lower():
            size = row.get("Sizedescription", "")
            expanded = row.get("Expandeddescription", "")
            price = row.get("Activeprice") or row.get("Price") or ""
            print(f"  {b} | {size} | {expanded} | ${price}")
