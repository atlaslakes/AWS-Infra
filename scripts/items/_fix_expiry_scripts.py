import os
import requests, json
requests.packages.urllib3.disable_warnings()

INSTANCES = ["https://www.karavanimports.com", "http://3.216.86.193"]
PASS = os.environ.get("ERP_ADMIN_PWD")

STOCK_ENTRY_SUBMIT_SCRIPT = '''\
if doc.docstatus == 1 and doc.stock_entry_type in ("Material Receipt", "Purchase Receipt", "Manufacture"):
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
                message: __("{0}: Expiry date {1} is PAST - item is expired!", [row.item_name || row.item_code, row.expiry_date]),
                indicator: "red"
            }, 12);
        } else if (row.expiry_date <= in30) {
            frappe.show_alert({
                message: __("{0}: Expires {1} - within 30 days!", [row.item_name || row.item_code, row.expiry_date]),
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
                var today = frappe.datetime.nowdate();
                var in30  = frappe.datetime.add_days(today, 30);
                r.message.forEach(function(sh) {
                    if (!sh.expiry_date) return;
                    if (sh.expiry_date < today) {
                        frappe.show_alert({
                            message: __("{0} has EXPIRED stock (exp. {1}, {2} cases)", [row.item_code, sh.expiry_date, sh.qty]),
                            indicator: "red"
                        }, 15);
                    } else if (sh.expiry_date <= in30) {
                        frappe.show_alert({
                            message: __("{0}: stock expiring {1} ({2} cases)", [row.item_code, sh.expiry_date, sh.qty]),
                            indicator: "orange"
                        }, 10);
                    }
                });
            }
        });
    }
});
'''

def uq(v): return requests.utils.quote(str(v), safe="")

for url in INSTANCES:
    label = "PROD" if "karavan" in url else "STAGING"
    print(f"\n[{label}]")
    s = requests.Session(); s.verify = False
    s.post(f"{url}/api/method/login", data={"usr":"Administrator","pwd":PASS}, timeout=20)

    # Server Script: Stock Entry submit
    name_ss = "Karavan-Stock-Entry-Expiry"
    chk = s.get(f"{url}/api/resource/Server%20Script/{uq(name_ss)}", timeout=10)
    body_ss = {"doctype":"Server Script","name":name_ss,"script_type":"DocType Event",
               "reference_doctype":"Stock Entry","doctype_event":"After Save",
               "enabled":1,"script":STOCK_ENTRY_SUBMIT_SCRIPT}
    if chk.status_code == 200:
        r = s.put(f"{url}/api/resource/Server%20Script/{uq(name_ss)}", json=body_ss, timeout=20)
    else:
        r = s.post(f"{url}/api/resource/Server%20Script", json=body_ss, timeout=20)
    print(f"  Server Script (submit): {r.status_code}")
    if r.status_code not in (200,201): print(" ",r.text[:200])

    # Client Script: Stock Entry
    name_cs1 = "Karavan-Expiry-StockEntry"
    chk1 = s.get(f"{url}/api/resource/Client%20Script/{uq(name_cs1)}", timeout=10)
    body_cs1 = {"doctype":"Client Script","name":name_cs1,"dt":"Stock Entry",
                "script":STOCK_ENTRY_CLIENT,"enabled":1,"view":"Form"}
    if chk1.status_code == 200:
        r1 = s.put(f"{url}/api/resource/Client%20Script/{uq(name_cs1)}", json=body_cs1, timeout=20)
    else:
        r1 = s.post(f"{url}/api/resource/Client%20Script", json=body_cs1, timeout=20)
    print(f"  Client Script (Stock Entry): {r1.status_code}")
    if r1.status_code not in (200,201): print(" ",r1.text[:200])

    # Client Script: Sales Invoice
    name_cs2 = "Karavan-Expiry-SalesInvoice"
    chk2 = s.get(f"{url}/api/resource/Client%20Script/{uq(name_cs2)}", timeout=10)
    body_cs2 = {"doctype":"Client Script","name":name_cs2,"dt":"Sales Invoice",
                "script":SALES_INVOICE_CLIENT,"enabled":1,"view":"Form"}
    if chk2.status_code == 200:
        r2 = s.put(f"{url}/api/resource/Client%20Script/{uq(name_cs2)}", json=body_cs2, timeout=20)
    else:
        r2 = s.post(f"{url}/api/resource/Client%20Script", json=body_cs2, timeout=20)
    print(f"  Client Script (Sales Invoice): {r2.status_code}")
    if r2.status_code not in (200,201): print(" ",r2.text[:200])

print("\nDone.")
