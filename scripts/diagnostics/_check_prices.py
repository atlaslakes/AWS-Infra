import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/resource/Item",
          params={"fields": '["name","item_name","standard_rate","custom_price"]',
                  "limit": 15}, timeout=15)
print("=== Sample prices ===")
for i in r.json().get("data", []):
    print(f"  {i['name']:14} standard_rate:{i.get('standard_rate')} custom_price:{i.get('custom_price')}")

r2 = s.get(f"{URL}/api/resource/Bin",
           params={"fields": '["item_code","actual_qty","warehouse"]', "limit": 10}, timeout=15)
print("\n=== Sample stock (Bin) ===")
for b in r2.json().get("data", []):
    print(f"  {b['item_code']:14} qty:{b.get('actual_qty')} wh:{b.get('warehouse')}")
