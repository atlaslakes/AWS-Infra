import os
"""
Sets up expiry date tracking across both ERPNext instances.

Creates:
  1. Custom DocType "Item Expiry Shipment"  — one row per received shipment
  2. Custom Field "expiry_date" on Stock Entry Detail  — entered at receiving time
  3. Server Script (DocType Event) on Stock Entry submit  — auto-creates shipment records
  4. Scheduled Server Script (Daily)  — sends in-app alerts 14 days before expiry
  5. Client Script on Stock Entry  — popup if expiry_date < 30 days when entering
  6. Client Script on Sales Invoice  — popup if item has expiring/expired shipments
"""
import requests, json, time

requests.packages.urllib3.disable_warnings()

INSTANCES = [
    "https://www.karavanimports.com",
    "http://3.216.86.193",
]
PASS = os.environ.get("ERP_ADMIN_PWD")

def session(url):
    s = requests.Session(); s.verify = False
    s.post(f"{url}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=20)
    return s

def uq(v): return requests.utils.quote(str(v), safe="")

def put_or_post(s, url, resource, name, body):
    """Update if exists, create otherwise."""
    chk = s.get(f"{url}/api/resource/{resource}/{uq(name)}", timeout=15)
    if chk.status_code == 200:
        r = s.put(f"{url}/api/resource/{resource}/{uq(name)}", json=body, timeout=30)
        return "updated", r.status_code
    else:
        r = s.post(f"{url}/api/resource/{resource}", json=body, timeout=30)
        return "created", r.status_code

# ──────────────────────────────────────────────────────────────────────────────
DAILY_SCRIPT = '''\
import frappe
from datetime import date, timedelta

today = frappe.utils.today()
warn_cutoff = frappe.utils.add_days(today, 14)

expired = frappe.db.get_all("Item Expiry Shipment",
    filters={"expiry_date": ["<", today], "status": "Active"},
    fields=["name", "item_code", "item_name", "expiry_date", "qty", "warehouse"])

expiring = frappe.db.get_all("Item Expiry Shipment",
    filters={"expiry_date": ["between", [today, warn_cutoff]], "status": "Active"},
    fields=["name", "item_code", "item_name", "expiry_date", "qty", "warehouse"])

admins = [u.name for u in frappe.db.get_all("User",
    filters={"enabled": 1, "user_type": "System User"}, fields=["name"])]

def notify(subject, content, doc_name):
    for user in admins:
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": subject,
            "email_content": content,
            "for_user": user,
            "type": "Alert",
            "document_type": "Item Expiry Shipment",
            "document_name": doc_name,
        }).insert(ignore_permissions=True)

for row in expired:
    days_ago = (frappe.utils.getdate(today) - frappe.utils.getdate(row.expiry_date)).days
    notify(
        f"EXPIRED: {row.item_name} expired {days_ago} day(s) ago",
        f"Item: {row.item_name}<br>Expiry: {row.expiry_date}<br>Qty: {row.qty}<br>Warehouse: {row.warehouse}",
        row.name
    )
    frappe.db.set_value("Item Expiry Shipment", row.name, "status", "Expired")

for row in expiring:
    days_left = (frappe.utils.getdate(row.expiry_date) - frappe.utils.getdate(today)).days
    notify(
        f"Expiry Warning: {row.item_name} expires in {days_left} day(s)",
        f"Item: {row.item_name}<br>Expiry: {row.expiry_date}<br>Qty: {row.qty}<br>Warehouse: {row.warehouse}",
        row.name
    )

frappe.db.commit()
'''

STOCK_ENTRY_SUBMIT_SCRIPT = '''\
# Auto-create Item Expiry Shipment records when stock is received
if doc.stock_entry_type in ("Material Receipt", "Purchase Receipt", "Manufacture"):
    for item in doc.items:
        if item.get("expiry_date") and item.t_warehouse:
            frappe.get_doc({
                "doctype": "Item Expiry Shipment",
                "item_code": item.item_code,
                "expiry_date": item.expiry_date,
                "received_date": doc.posting_date,
                "qty": item.qty,
                "warehouse": item.t_warehouse,
                "reference": doc.name,
                "status": "Active",
            }).insert(ignore_permissions=True)
    frappe.db.commit()
'''

STOCK_ENTRY_CLIENT = '''\
frappe.ui.form.on("Stock Entry Detail", {
    expiry_date: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (!row.expiry_date) return;
        var today = frappe.datetime.nowdate();
        var in30  = frappe.datetime.add_days(today, 30);
        if (row.expiry_date < today) {
            frappe.show_alert({
                message: __("⛔ {0}: Expiry date {1} is already PAST — item is expired!", [row.item_name || row.item_code, row.expiry_date]),
                indicator: "red"
            }, 12);
        } else if (row.expiry_date <= in30) {
            frappe.show_alert({
                message: __("⚠️ {0}: Expires on {1} — within 30 days!", [row.item_name || row.item_code, row.expiry_date]),
                indicator: "orange"
            }, 8);
        }
    }
});
'''

SALES_INVOICE_CLIENT = '''\
frappe.ui.form.on("Sales Invoice Item", {
    item_code: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (!row.item_code) return;
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Item Expiry Shipment",
                filters: [["item_code","=",row.item_code],["status","in",["Active","Expired"]]],
                fields: ["name","expiry_date","qty","status"],
                order_by: "expiry_date asc",
                limit: 10
            },
            callback: function(r) {
                if (!r.message || !r.message.length) return;
                var today  = frappe.datetime.nowdate();
                var in30   = frappe.datetime.add_days(today, 30);
                r.message.forEach(function(s) {
                    if (!s.expiry_date) return;
                    if (s.expiry_date < today) {
                        frappe.show_alert({
                            message: __("⛔ {0} has EXPIRED stock (exp. {1}, {2} cases) — do not sell!", [row.item_code, s.expiry_date, s.qty]),
                            indicator: "red"
                        }, 15);
                    } else if (s.expiry_date <= in30) {
                        frappe.show_alert({
                            message: __("⚠️ {0} has stock expiring {1} ({2} cases)", [row.item_code, s.expiry_date, s.qty]),
                            indicator: "orange"
                        }, 10);
                    }
                });
            }
        });
    }
});
'''

# ──────────────────────────────────────────────────────────────────────────────
for url in INSTANCES:
    label = "PROD" if "karavan" in url else "STAGING"
    print(f"\n{'='*60}")
    print(f"  {label}: {url}")
    print(f"{'='*60}")
    s = session(url)

    # ── 1. Custom DocType: Item Expiry Shipment ────────────────────────────────
    print("\n[1] Custom DocType: Item Expiry Shipment...")
    dt_body = {
        "doctype": "DocType",
        "name": "Item Expiry Shipment",
        "module": "Stock",
        "custom": 1,
        "is_submittable": 0,
        "autoname": "format:EXP-{item_code}-{####}",
        "title_field": "item_name",
        "fields": [
            {"fieldname":"item_code","label":"Item","fieldtype":"Link","options":"Item","reqd":1,"in_list_view":1},
            {"fieldname":"item_name","label":"Item Name","fieldtype":"Data","fetch_from":"item_code.item_name","in_list_view":1},
            {"fieldname":"col1","fieldtype":"Column Break"},
            {"fieldname":"expiry_date","label":"Expiry Date","fieldtype":"Date","reqd":1,"in_list_view":1,"bold":1},
            {"fieldname":"status","label":"Status","fieldtype":"Select",
             "options":"Active\nExpiring\nExpired\nConsumed","default":"Active","in_list_view":1},
            {"fieldname":"sec1","fieldtype":"Section Break"},
            {"fieldname":"received_date","label":"Received Date","fieldtype":"Date","default":"Today"},
            {"fieldname":"qty","label":"Quantity (Cases)","fieldtype":"Float","in_list_view":1},
            {"fieldname":"col2","fieldtype":"Column Break"},
            {"fieldname":"warehouse","label":"Warehouse","fieldtype":"Link","options":"Warehouse"},
            {"fieldname":"reference","label":"Stock Entry Reference","fieldtype":"Data"},
            {"fieldname":"sec2","fieldtype":"Section Break"},
            {"fieldname":"notes","label":"Notes","fieldtype":"Small Text"},
        ],
        "permissions": [
            {"role":"Stock User","read":1,"write":1,"create":1,"delete":0,"submit":0},
            {"role":"System Manager","read":1,"write":1,"create":1,"delete":1},
        ],
    }
    action, code = put_or_post(s, url, "DocType", "Item Expiry Shipment", dt_body)
    print(f"  {action}: {code}")
    if code not in (200, 201):
        chk2 = s.get(f"{url}/api/resource/DocType/Item%20Expiry%20Shipment", timeout=10)
        print(f"  (already exists: {chk2.status_code == 200})")
    time.sleep(1)

    # ── 2. Custom Field: expiry_date on Stock Entry Detail ─────────────────────
    print("\n[2] Custom Field: expiry_date on Stock Entry Detail...")
    cf_body = {
        "doctype": "Custom Field",
        "dt": "Stock Entry Detail",
        "fieldname": "expiry_date",
        "label": "Expiry Date",
        "fieldtype": "Date",
        "insert_after": "item_name",
        "in_list_view": 1,
        "bold": 0,
        "description": "Expiry date for this shipment/batch",
    }
    chk = s.get(f"{url}/api/resource/Custom%20Field/Stock Entry Detail-expiry_date", timeout=10)
    if chk.status_code == 200:
        r = s.put(f"{url}/api/resource/Custom%20Field/Stock Entry Detail-expiry_date",
                  json=cf_body, timeout=20)
        print(f"  updated: {r.status_code}")
    else:
        r = s.post(f"{url}/api/resource/Custom%20Field", json=cf_body, timeout=20)
        print(f"  created: {r.status_code}")
        if r.status_code not in (200, 201):
            print("  WARN:", r.text[:150])

    # ── 3. Server Script: Stock Entry on_submit ────────────────────────────────
    print("\n[3] Server Script: Stock Entry on_submit -> create expiry records...")
    ss1 = {
        "doctype": "Server Script",
        "name": "Karavan Stock Entry Expiry",
        "script_type": "DocType Event",
        "reference_doctype": "Stock Entry",
        "doctype_event": "on_submit",
        "enabled": 1,
        "script": STOCK_ENTRY_SUBMIT_SCRIPT,
    }
    action, code = put_or_post(s, url, "Server%20Script", "Karavan Stock Entry Expiry", ss1)
    print(f"  {action}: {code}")

    # ── 4. Scheduled Server Script: Daily expiry check ────────────────────────
    print("\n[4] Scheduled Server Script: Daily expiry notifications...")
    ss2 = {
        "doctype": "Server Script",
        "name": "Karavan Daily Expiry Check",
        "script_type": "Scheduler Event",
        "event_frequency": "Daily",
        "enabled": 1,
        "script": DAILY_SCRIPT,
    }
    action, code = put_or_post(s, url, "Server%20Script", "Karavan Daily Expiry Check", ss2)
    print(f"  {action}: {code}")

    # ── 5. Client Script: Stock Entry expiry warning ───────────────────────────
    print("\n[5] Client Script: Stock Entry popup warning...")
    cs1_chk = s.get(f"{url}/api/resource/Client%20Script",
                    params={"filters": '[["dt","=","Stock Entry"],["name","like","Karavan%"]]',
                            "fields": '["name"]'}, timeout=10).json().get("data", [])
    cs1_body = {
        "doctype": "Client Script",
        "dt": "Stock Entry",
        "script": STOCK_ENTRY_CLIENT,
        "enabled": 1,
        "view": "Form",
    }
    if cs1_chk:
        r = s.put(f"{url}/api/resource/Client%20Script/{uq(cs1_chk[0]['name'])}",
                  json=cs1_body, timeout=20)
        print(f"  updated: {r.status_code}")
    else:
        r = s.post(f"{url}/api/resource/Client%20Script", json=cs1_body, timeout=20)
        print(f"  created: {r.status_code}")

    # ── 6. Client Script: Sales Invoice expiry warning ────────────────────────
    print("\n[6] Client Script: Sales Invoice popup warning...")
    cs2_chk = s.get(f"{url}/api/resource/Client%20Script",
                    params={"filters": '[["dt","=","Sales Invoice"],["name","like","Karavan%Expir%"]]',
                            "fields": '["name"]'}, timeout=10).json().get("data", [])
    cs2_body = {
        "doctype": "Client Script",
        "dt": "Sales Invoice",
        "script": SALES_INVOICE_CLIENT,
        "enabled": 1,
        "view": "Form",
    }
    if cs2_chk:
        r = s.put(f"{url}/api/resource/Client%20Script/{uq(cs2_chk[0]['name'])}",
                  json=cs2_body, timeout=20)
        print(f"  updated: {r.status_code}")
    else:
        r = s.post(f"{url}/api/resource/Client%20Script", json=cs2_body, timeout=20)
        print(f"  created: {r.status_code}")
        if r.status_code not in (200, 201):
            print("  WARN:", r.text[:200])

    print(f"\n  Done: {label}")

print("\n" + "="*60)
print("  EXPIRY TRACKING SETUP COMPLETE")
print("  Workflow:")
print("  1. Stock > Stock Entry (Material Receipt) - enter Expiry Date per item")
print("  2. On submit, shipment records auto-created in Item Expiry Shipment")
print("  3. Daily scheduler sends in-app alerts 14 days before expiry")
print("  4. Sales Invoice shows popup if added item has expiring/expired stock")
print("="*60)
