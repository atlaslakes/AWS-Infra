import os, requests, json
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

item_code = "BEAN-0001"

# Add an already-expired lot (expiry in the past relative to today 2026-06-30)
resp = s.post(f"{URL}/api/resource/Item Lot", json={
    "item_code": item_code,
    "received_date": "2025-01-01",
    "expiry_date": "2026-01-01",   # already expired
    "cases_received": 5,
    "notes": "TEST LOT - already expired",
}, timeout=15)
name = resp.json()["data"]["name"] if resp.status_code in (200,201) else None
print("Created expired lot:", name, resp.status_code)

with open("_test_lots_created.json") as f:
    lots = json.load(f)
if name:
    lots.append(name)
    with open("_test_lots_created.json", "w") as f:
        json.dump(lots, f)

# Check Inventory Manager still shows 2026-08-01, NOT the expired 2026-01-01
r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows = [row for row in r.json().get("message", {}).get("result", []) if isinstance(row, dict)]
row = next((x for x in rows if x.get("item_id") == item_code), None)
expiry = row.get("nearest_expiry") if row else "?"
print(f"Nearest Expiry for {item_code}: {expiry}  (should still be 2026-08-01, ignoring the expired one)")
print("Correct:", str(expiry) == "2026-08-01")
