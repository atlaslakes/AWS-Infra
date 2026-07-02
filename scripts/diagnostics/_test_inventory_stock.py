import os, requests, time
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

# ── 1. Pick a test item that has stock ────────────────────────────────────────
r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows = r.json().get("message", {}).get("result", [])
# Find first item with Cases On Hand > 5
test_item = next((row for row in rows if isinstance(row, dict) and int(row.get("cases_on_hand", 0) or 0) > 5), None)

if not test_item:
    print("No item with stock > 5 found"); exit(1)

item_code  = test_item["item_id"]
item_name  = test_item["description"]
before_qty = int(test_item.get("cases_on_hand", 0) or 0)
print(f"Test item : {item_code} — {item_name}")
print(f"Before    : {before_qty} cases on hand\n")

# ── 2. Get customer for invoice ───────────────────────────────────────────────
cust_r = s.get(f"{URL}/api/resource/Customer", params={"limit": 1, "fields": '["name"]'}, timeout=15)
customer = cust_r.json().get("data", [{}])[0].get("name", "")
if not customer:
    print("No customer found"); exit(1)
print(f"Customer  : {customer}")

# ── 3. Submit a test Sales Invoice for 2 cases ───────────────────────────────
print("\n[1] Creating Sales Invoice for 2 cases...")
inv = s.post(f"{URL}/api/resource/Sales Invoice", json={
    "customer": customer,
    "posting_date": "2026-06-30",
    "due_date": "2026-07-30",
    "items": [{
        "item_code": item_code,
        "qty": 2,
        "rate": float(test_item.get("price/item") or 1),
        "warehouse": "Stores - AL",
    }],
    "update_stock": 1,
}, timeout=30)

if inv.status_code not in (200, 201):
    print(f"Failed to create invoice: {inv.status_code} {inv.text[:300]}"); exit(1)

inv_name = inv.json()["data"]["name"]
print(f"  Created: {inv_name}")

# Re-fetch latest doc then submit (avoids timestamp mismatch)
fresh = s.get(f"{URL}/api/resource/Sales Invoice/{inv_name}", timeout=15).json().get("data", {})
sub = s.post(f"{URL}/api/method/frappe.client.submit", json={"doc": fresh}, timeout=30)
print(f"  Submit status: {sub.status_code}")
if sub.status_code not in (200, 201):
    print(f"  Submit error: {sub.text[:300]}")
time.sleep(3)

# ── 4. Read Inventory Manager after submit ───────────────────────────────────
print("\n[2] Reading Inventory Manager after submit...")
r2 = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
           params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows2 = r2.json().get("message", {}).get("result", [])
after_row = next((row for row in rows2 if isinstance(row, dict) and row.get("item_id") == item_code), None)
after_qty = int(after_row.get("cases_on_hand", 0) or 0) if after_row else "?"
print(f"  After submit : {after_qty} cases on hand")
print(f"  Change       : {before_qty} -> {after_qty}  (expected {before_qty - 2})")
correct = after_qty == before_qty - 2
print(f"  Correct      : {'YES' if correct else 'NO'}\n")

# ── 5. Cancel the invoice to restore stock ───────────────────────────────────
print("[3] Cancelling test invoice to restore stock...")
cancel = s.post(f"{URL}/api/method/frappe.client.cancel",
                json={"doctype": "Sales Invoice", "name": inv_name}, timeout=30)
print(f"  Cancel status: {cancel.status_code}")
time.sleep(3)

r3 = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
           params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
rows3 = r3.json().get("message", {}).get("result", [])
restored_row = next((row for row in rows3 if isinstance(row, dict) and row.get("item_id") == item_code), None)
restored_qty = int(restored_row.get("cases_on_hand", 0) or 0) if restored_row else "?"
print(f"  After cancel : {restored_qty} cases on hand")
print("  Restored     : %s\n" % ("YES" if restored_qty == before_qty else "NO"))

print("=" * 50)
print(f"SUMMARY  {item_code} — {item_name}")
print(f"  Before submit : {before_qty}")
print(f"  After submit  : {after_qty}  (ordered 2)")
print(f"  After cancel  : {restored_qty}")
print("=" * 50)
