import os, requests, json
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

with open("_test_lots_created.json") as f:
    lots = json.load(f)

print(f"Deleting {len(lots)} test lots...")
for name in lots:
    r = s.delete(f"{URL}/api/resource/Item Lot/{name}", timeout=15)
    print(f"  {name}: {r.status_code}")

# Verify Inventory Manager no longer shows any expiry for the test items
r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows = [row for row in r.json().get("message", {}).get("result", []) if isinstance(row, dict)]
for item_code in ["BEAN-0001", "BEAN-0007", "BEAN-0005"]:
    row = next((x for x in rows if x.get("item_id") == item_code), None)
    expiry = row.get("nearest_expiry") if row else "?"
    print(f"{item_code} Nearest Expiry after cleanup: {expiry}  (should be None)")

print("\nDONE")
