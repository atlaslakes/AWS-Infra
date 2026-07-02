import os
import requests, json, re, csv
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# 1. Check what price lists exist
print("=== Price Lists ===")
pl = s.get(f"{URL}/api/resource/Price List", params={"fields": '["name","currency","enabled","selling","buying"]', "limit": 50}, timeout=15)
for p in pl.json().get("data", []):
    print(f"  {p['name']} | selling:{p.get('selling')} | buying:{p.get('buying')} | enabled:{p.get('enabled')}")

# 2. Check one failed item price write error
print("\n=== Item Price write test (BEV-0007) ===")
r = s.post(f"{URL}/api/resource/Item Price", json={
    "item_code": "BEV-0007",
    "price_list": "Standard Selling",
    "price_list_rate": 3.99,
    "selling": 1,
    "currency": "USD",
    "uom": "Nos",
}, timeout=15)
print(f"Status: {r.status_code}")
try:
    d = r.json()
    print("Exception:", d.get("exception", "")[:200])
    print("Message:", d.get("message", "")[:200])
except:
    print(r.text[:300])

# 3. Check PUT on an item for standard_rate error
print("\n=== Item PUT test (BEV-0007) ===")
r2 = s.put(f"{URL}/api/resource/Item/BEV-0007", json={"standard_rate": 3.99, "custom_price": 3.99}, timeout=15)
print(f"Status: {r2.status_code}")
if r2.status_code != 200:
    try:
        d = r2.json()
        print("Exception:", d.get("exception", "")[:300])
    except:
        print(r2.text[:300])

# 4. Check California Garden items in CSV to understand why they don't match
print("\n=== CSV check: California Garden ===")
with open("Data_06_23.csv", encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f)
    cg_rows = [row for row in reader if "California Garden" in (row.get("Branddescription") or "")
               and "Fava" in (row.get("Expandeddescription") or "")]
    for row in cg_rows[:10]:
        print(f"  Brand:{row['Branddescription']} | Size:{row['Sizedescription']} | Desc:{row['Expandeddescription']} | Price:{row.get('Activeprice','?')}")

# 5. Check what UOM BEV-0007 has
print("\n=== BEV-0007 details ===")
item = s.get(f"{URL}/api/resource/Item/BEV-0007", timeout=15).json().get("data", {})
print(f"  stock_uom: {item.get('stock_uom')}")
print(f"  uoms: {item.get('uoms')}")
print(f"  brand: {item.get('brand')}, name: {item.get('item_name')}, size: {item.get('package_size')}")
