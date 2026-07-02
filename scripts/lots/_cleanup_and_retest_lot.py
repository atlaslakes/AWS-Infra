import os, requests, json
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

# ── 1. Delete the old test lots (LOT-0009..0014) — created before stock-wiring existed ──
with open("_test_lots_created.json") as f:
    old_lots = json.load(f)

print("Deleting old test lots (pre-wiring, no stock_entry):")
for name in old_lots:
    r = s.delete(f"{URL}/api/resource/Item Lot/{name}", timeout=15)
    print(f"  {name}: {r.status_code}")

# ── 2. Pick a test item, read its current Cases On Hand ──────────────────────
item_code = "BEAN-0001"
r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows = [row for row in r.json().get("message", {}).get("result", []) if isinstance(row, dict)]
before_row = next((x for x in rows if x.get("item_id") == item_code), None)
before_qty = before_row.get("cases_on_hand") if before_row else None
print(f"\n{item_code} Cases On Hand BEFORE new lot: {before_qty}")

# ── 3. Create ONE new lot — should auto-create a Material Receipt and bump stock ──
print("\nCreating new test lot (5 cases, expiry 2026-12-25)...")
resp = s.post(f"{URL}/api/resource/Item Lot", json={
    "item_code": item_code,
    "received_date": "2026-06-30",
    "expiry_date": "2026-12-25",
    "cases_received": 5,
    "notes": "TEST LOT - stock wiring verification",
}, timeout=20)
print("Create status:", resp.status_code)
if resp.status_code not in (200, 201):
    print("FAILED:", resp.text[:400]); exit(1)

lot = resp.json()["data"]
lot_name = lot["name"]
print("Lot:", lot_name)

# Save for later cleanup
with open("_test_lots_created.json", "w") as f:
    json.dump([lot_name], f)

# ── 4. Re-fetch the lot to see if stock_entry got linked ─────────────────────
detail = s.get(f"{URL}/api/resource/Item Lot/{lot_name}", timeout=15).json().get("data", {})
print("Linked Stock Entry:", detail.get("stock_entry"))

# ── 5. Read Cases On Hand again ───────────────────────────────────────────────
r2 = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
           params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows2 = [row for row in r2.json().get("message", {}).get("result", []) if isinstance(row, dict)]
after_row = next((x for x in rows2 if x.get("item_id") == item_code), None)
after_qty = after_row.get("cases_on_hand") if after_row else None
expiry = after_row.get("nearest_expiry") if after_row else None

print(f"\n{item_code} Cases On Hand AFTER new lot: {after_qty}")
print(f"Expected: {before_qty} + 5 = {(before_qty or 0) + 5}")
print(f"Correct: {after_qty == (before_qty or 0) + 5}")
print(f"Nearest Expiry: {expiry}")
