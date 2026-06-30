import os
import requests
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# Check bin quantities for a few items
print("=== Bin quantities (should match Excel cases) ===")
items_to_check = ["BEAN-0002","BEAN-0003","BEAN-0006","RICE-0001","RICE-0003","RICE-0004"]
for code in items_to_check:
    r = s.get(f"{URL}/api/resource/Bin",
              params={"fields": '["item_code","actual_qty","warehouse"]',
                      "filters": f'[["item_code","=","{code}"]]'}, timeout=10)
    bins = r.json().get("data", [])
    if bins:
        for b in bins:
            print(f"  {b['item_code']:14} actual_qty={b['actual_qty']}  wh={b['warehouse']}")
    else:
        print(f"  {code:14} no bin record")

# Run the report and check first 10 rows
print("\n=== Inventory Manager report (first 10) ===")
r2 = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
           params={"report_name": "Inventory Manager", "ignore_prepared_report": 1},
           timeout=60)
msg = r2.json().get("message", {})
rows = [row for row in msg.get("result", []) if isinstance(row, dict)]
for row in rows[:10]:
    print(f"  {str(row.get('item_code','')):<14} cases_on_hand={row.get('cases_on_hand')}  {row.get('item_name','')[:35]}")
