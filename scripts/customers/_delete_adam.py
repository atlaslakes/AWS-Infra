import os
import requests, json, time
requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

def q(n): return requests.utils.quote(str(n), safe="")

def get_all(dt, filters, fields=["name"]):
    r = s.get(f"{URL}/api/resource/{q(dt)}",
              params={"fields": json.dumps(fields),
                      "filters": json.dumps(filters), "limit": 500}, timeout=15)
    return r.json().get("data", [])

def cancel_doc(dt, name):
    r = s.post(f"{URL}/api/method/frappe.client.cancel",
               json={"doctype": dt, "name": name}, timeout=15)
    return r.status_code in (200, 201)

def delete_doc(dt, name):
    r = s.delete(f"{URL}/api/resource/{q(dt)}/{q(name)}", timeout=15)
    ok = r.status_code in (200, 202, 204)
    if not ok:
        try:
            msg = r.json().get("exception", r.text[:120])
        except:
            msg = r.text[:120]
        print(f"    ERR delete {dt}/{name}: {msg}")
    return ok

CUSTOMER = "adam"
deleted = 0
errors  = 0

# ── 1. Submitted documents — cancel first, then delete ────────────────────────
for dt in ["Sales Invoice", "Sales Order", "Delivery Note", "Purchase Order"]:
    rows = get_all(dt, [["customer", "=", CUSTOMER]], ["name", "docstatus"])
    for row in rows:
        name = row["name"]
        status = row.get("docstatus", 0)
        print(f"  {dt}/{name} docstatus={status}")
        if status == 1:
            ok = cancel_doc(dt, name)
            print(f"    cancel: {'ok' if ok else 'FAIL'}")
        if delete_doc(dt, name):
            print(f"    deleted")
            deleted += 1
        else:
            errors += 1

# Payment Entries (party = customer)
for row in get_all("Payment Entry", [["party", "=", CUSTOMER], ["party_type", "=", "Customer"]], ["name", "docstatus"]):
    name = row["name"]
    if row.get("docstatus") == 1:
        cancel_doc("Payment Entry", name)
    if delete_doc("Payment Entry", name):
        deleted += 1
    else:
        errors += 1

# ── 2. Draft/other documents ──────────────────────────────────────────────────
for dt, field in [
    ("Quotation",        "party_name"),
    ("Lead",             "customer"),
    ("Communication",    "reference_name"),
    ("Comment",          "reference_name"),
    ("Activity Log",     "reference_name"),
]:
    try:
        rows = get_all(dt, [[field, "=", CUSTOMER]])
        for row in rows:
            name = row["name"]
            if delete_doc(dt, name):
                deleted += 1
            else:
                errors += 1
    except Exception as e:
        pass  # doctype might not exist

# ── 3. Contact linked to adam ─────────────────────────────────────────────────
# Contact "adam-adam"
contacts = get_all("Contact", [["link_name", "=", CUSTOMER]])
for row in contacts:
    name = row["name"]
    print(f"  Contact/{name}")
    if delete_doc("Contact", name):
        print(f"    deleted")
        deleted += 1
    else:
        errors += 1

# Also check by contact name
for row in get_all("Contact", [["name", "like", f"%{CUSTOMER}%"]]):
    name = row["name"]
    print(f"  Contact/{name} (name match)")
    if delete_doc("Contact", name):
        print(f"    deleted")
        deleted += 1
    else:
        errors += 1

# ── 4. Address linked to adam ─────────────────────────────────────────────────
for row in get_all("Address", [["link_name", "=", CUSTOMER]]):
    name = row["name"]
    if delete_doc("Address", name):
        deleted += 1
    else:
        errors += 1

# ── 5. Customer itself ────────────────────────────────────────────────────────
print(f"\n  Customer/{CUSTOMER}")
if delete_doc("Customer", CUSTOMER):
    print(f"    deleted")
    deleted += 1
else:
    errors += 1

print(f"\n=== Done: {deleted} records deleted, {errors} errors ===")
