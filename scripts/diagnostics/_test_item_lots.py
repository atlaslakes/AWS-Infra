import os, requests, json
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

# ── 1. Pick a few items with stock to test on ─────────────────────────────────
r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows = [row for row in r.json().get("message", {}).get("result", []) if isinstance(row, dict)]
candidates = [row for row in rows if int(row.get("cases_on_hand", 0) or 0) > 0][:3]

if not candidates:
    print("No items with stock found"); exit(1)

print("Test items:")
for c in candidates:
    print(f"  {c['item_id']} — {c['description']}  (qty={c['cases_on_hand']})")

# ── 2. Create 2 lots per item with DIFFERENT expiry dates (simulating two shipments) ──
created_lots = []
test_data = [
    {"received_date": "2026-01-15", "expiry_date": "2026-08-01", "cases_received": 10, "notes": "TEST LOT - old shipment"},
    {"received_date": "2026-06-01", "expiry_date": "2027-03-01", "cases_received": 15, "notes": "TEST LOT - newer shipment"},
]

print("\nCreating test lots...")
for c in candidates:
    item_code = c["item_id"]
    for td in test_data:
        payload = {"item_code": item_code, **td}
        resp = s.post(f"{URL}/api/resource/Item Lot", json=payload, timeout=15)
        if resp.status_code in (200, 201):
            name = resp.json()["data"]["name"]
            created_lots.append(name)
            print(f"  {name}: {item_code} expiry={td['expiry_date']} qty={td['cases_received']}")
        else:
            print(f"  FAILED {item_code}: {resp.status_code} {resp.text[:150]}")

# Save lot names so we can clean up later
with open("_test_lots_created.json", "w") as f:
    json.dump(created_lots, f)
print(f"\nSaved {len(created_lots)} lot names to _test_lots_created.json")

# ── 3. Read Inventory Manager and confirm Nearest Expiry shows the EARLIEST date ──
print("\nVerifying Nearest Expiry on Inventory Manager...")
r2 = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
           params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows2 = [row for row in r2.json().get("message", {}).get("result", []) if isinstance(row, dict)]

for c in candidates:
    item_code = c["item_id"]
    row = next((x for x in rows2 if x.get("item_id") == item_code), None)
    expiry = row.get("nearest_expiry") if row else "?"
    expected = "2026-08-01"  # the earlier of the two lots
    correct = str(expiry) == expected
    print(f"  {item_code}: Nearest Expiry = {expiry}  (expected {expected})  {'OK' if correct else 'MISMATCH'}")

print("\nDONE — test lots are live. Run _cleanup_test_lots.py to remove them.")
