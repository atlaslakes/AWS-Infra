import os
import requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in")

# Server Script: deduct cases_on_hand on Sales Invoice submit
submit_script = """
for item in doc.items:
    if not item.item_code:
        continue
    qty = item.qty or 0
    if qty <= 0:
        continue
    current = frappe.db.get_value("Item", item.item_code, "cases_on_hand") or 0
    new_val = max(0, int(current) - int(qty))
    frappe.db.set_value("Item", item.item_code, "cases_on_hand", new_val)
"""

# Server Script: restore cases_on_hand on Sales Invoice cancel
cancel_script = """
for item in doc.items:
    if not item.item_code:
        continue
    qty = item.qty or 0
    if qty <= 0:
        continue
    current = frappe.db.get_value("Item", item.item_code, "cases_on_hand") or 0
    new_val = int(current) + int(qty)
    frappe.db.set_value("Item", item.item_code, "cases_on_hand", new_val)
"""

scripts = [
    {
        "name_hint": "Deduct Cases On Hand on Invoice Submit",
        "script_type": "DocType Event",
        "reference_doctype": "Sales Invoice",
        "doctype_event": "After Submit",
        "script": submit_script,
    },
    {
        "name_hint": "Restore Cases On Hand on Invoice Cancel",
        "script_type": "DocType Event",
        "reference_doctype": "Sales Invoice",
        "doctype_event": "After Cancel",
        "script": cancel_script,
    },
]

for sc in scripts:
    # Check if already exists
    existing = s.get(f"{URL}/api/resource/Server Script",
        params={"filters": f'[["name","=","{sc["name_hint"]}"]]',
                "fields": '["name"]'}, timeout=15).json().get("data", [])

    if existing:
        name = existing[0]["name"]
        r = s.put(f"{URL}/api/resource/Server Script/{name}",
                  json={"script": sc["script"], "disabled": 0}, timeout=15)
        print(f"Updated '{name}': {r.status_code}")
    else:
        payload = {
            "name": sc["name_hint"],
            "script_type": sc["script_type"],
            "reference_doctype": sc["reference_doctype"],
            "doctype_event": sc["doctype_event"],
            "script": sc["script"],
            "disabled": 0,
        }
        r = s.post(f"{URL}/api/resource/Server Script", json=payload, timeout=15)
        if r.status_code in (200, 201):
            created_name = r.json().get("data", {}).get("name", "?")
            print(f"Created '{sc['name_hint']}' as '{created_name}': OK")
        else:
            print(f"Failed '{sc['name_hint']}': {r.status_code} {r.text[:200]}")

print("\nDone. Submit a Sales Invoice to test deduction.")
