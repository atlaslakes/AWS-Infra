import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Check BEAN-0002 full item fields
r = s.get(f"{URL}/api/resource/Item/BEAN-0002", timeout=15)
data = r.json().get("data", {})
# Print all fields that might have barcode/UPC
for k, v in data.items():
    if v and (str(v).strip() not in ("", "0", "0.0", "None")):
        if any(x in k.lower() for x in ["bar","upc","code","scan"]) or k == "barcodes":
            print(f"  {k}: {v}")

# Also print barcodes child table
print("\nbarcodes field:", data.get("barcodes"))

# Try direct query
r2 = s.get(f"{URL}/api/resource/Item Barcode",
           params={"fields": '["parent","barcode","upc"]', "limit": 5}, timeout=15)
print("\nItem Barcode sample:", r2.json())
