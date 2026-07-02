import os, requests, json, time
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

item_code = "BEAN-0001"

# Cancel+delete the stuck draft Stock Entry from the failed run
stuck_se = "MAT-STE-2026-00010"
r = s.get(f"{URL}/api/resource/Stock Entry/{stuck_se}", timeout=15)
docstatus = r.json().get("data", {}).get("docstatus")
print(f"Stuck SE {stuck_se} docstatus={docstatus}")
if docstatus == 0:
    s.delete(f"{URL}/api/resource/Stock Entry/{stuck_se}", timeout=15)
    print(f"Deleted draft {stuck_se}")

# Delete the linked lot too and save to recreate cleanly
with open("_test_lots_created.json") as f:
    lots = json.load(f)
for name in lots:
    r = s.delete(f"{URL}/api/resource/Item Lot/{name}", timeout=15)
    print(f"Deleted lot {name}: {r.status_code}")

# Read stock before
def get_qty(item):
    r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
              params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
    rows = [x for x in r.json().get("message", {}).get("result", []) if isinstance(x, dict)]
    row = next((x for x in rows if x.get("item_id") == item), None)
    return (row.get("cases_on_hand"), row.get("nearest_expiry")) if row else (None, None)

before_qty, _ = get_qty(item_code)
print(f"\n{item_code} Cases On Hand BEFORE: {before_qty}")

# Create new lot
print("\nCreating new test lot (7 cases, expiry 2026-11-01)...")
resp = s.post(f"{URL}/api/resource/Item Lot", json={
    "item_code": item_code,
    "received_date": "2026-06-30",
    "expiry_date": "2026-11-01",
    "cases_received": 7,
    "notes": "TEST - stock wiring live test",
}, timeout=20)
print("Create status:", resp.status_code)
if resp.status_code not in (200, 201):
    print("FAILED:", resp.text[:400]); exit(1)

lot = resp.json()["data"]
lot_name = lot["name"]
print("Lot:", lot_name)
with open("_test_lots_created.json", "w") as f:
    json.dump([lot_name], f)

# Wait for background submit job to complete (poll up to 45s)
detail = s.get(f"{URL}/api/resource/Item Lot/{lot_name}", timeout=15).json().get("data", {})
se_name = detail.get("stock_entry")
print("Linked Stock Entry:", se_name)

if se_name:
    print("Polling for submit completion...")
    for i in range(9):
        time.sleep(5)
        r = s.get(f"{URL}/api/resource/Stock Entry/{se_name}", timeout=15)
        ds = r.json().get("data", {}).get("docstatus")
        print(f"  [{i+1}] docstatus={ds}")
        if ds == 1:
            print("  Submitted!")
            break

after_qty, expiry = get_qty(item_code)
print(f"\n{item_code} Cases On Hand AFTER: {after_qty}")
print(f"Expected: {before_qty} + 7 = {(before_qty or 0) + 7}")
print(f"Stock correct: {after_qty == (before_qty or 0) + 7}")
print(f"Nearest Expiry: {expiry}")
