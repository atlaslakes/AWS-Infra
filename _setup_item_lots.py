"""
Creates the 'Item Lot' custom Doctype in ERPNext for tracking shipment expiry dates.
- One lot per shipment per item
- Staff create lots when receiving inventory
- Inventory Manager gains a 'Nearest Expiry' column
- No changes to invoicing or Base44
"""
import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote_script = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# ── 1. Create Item Lot Doctype ────────────────────────────────────────────────
if frappe.db.exists("DocType", "Item Lot"):
    print("Item Lot doctype already exists, updating...")
    frappe.delete_doc("DocType", "Item Lot", force=True, ignore_permissions=True)

dt = frappe.get_doc({
    "doctype": "DocType",
    "name": "Item Lot",
    "module": "Stock",
    "custom": 1,
    "is_submittable": 0,
    "autoname": "format:LOT-{####}",
    "title_field": "item_code",
    "fields": [
        {
            "fieldname": "item_code",
            "fieldtype": "Link",
            "label": "Item",
            "options": "Item",
            "reqd": 1,
            "in_list_view": 1,
            "in_standard_filter": 1,
            "search_index": 1,
        },
        {
            "fieldname": "item_name",
            "fieldtype": "Data",
            "label": "Item Name",
            "fetch_from": "item_code.item_name",
            "read_only": 1,
            "in_list_view": 1,
        },
        {
            "fieldname": "col_break_1",
            "fieldtype": "Column Break",
        },
        {
            "fieldname": "received_date",
            "fieldtype": "Date",
            "label": "Received Date",
            "reqd": 1,
            "in_list_view": 1,
            "default": "Today",
        },
        {
            "fieldname": "expiry_date",
            "fieldtype": "Date",
            "label": "Expiry Date",
            "in_list_view": 1,
            "in_standard_filter": 1,
            "bold": 1,
        },
        {
            "fieldname": "sec_break_1",
            "fieldtype": "Section Break",
            "label": "Shipment Details",
        },
        {
            "fieldname": "cases_received",
            "fieldtype": "Int",
            "label": "Cases Received",
            "reqd": 1,
            "in_list_view": 1,
        },
        {
            "fieldname": "supplier",
            "fieldtype": "Link",
            "label": "Supplier",
            "options": "Supplier",
        },
        {
            "fieldname": "col_break_2",
            "fieldtype": "Column Break",
        },
        {
            "fieldname": "purchase_order",
            "fieldtype": "Data",
            "label": "PO / Reference",
        },
        {
            "fieldname": "notes",
            "fieldtype": "Small Text",
            "label": "Notes",
        },
    ],
    "permissions": [
        {"role": "Stock Manager",   "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
        {"role": "Stock User",      "read": 1, "write": 1, "create": 1, "report": 1},
        {"role": "System Manager",  "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
    ],
})
dt.flags.ignore_permissions = True
dt.insert(ignore_permissions=True)
frappe.db.commit()
print("Item Lot doctype created")

# ── 2. Update Inventory Manager query report ──────────────────────────────────
rpt = frappe.get_doc("Report", "Inventory Manager")
rpt.query = '''SELECT
    i.item_code   AS "Item ID:Link/Item:130",
    i.item_name   AS "Description:Data:250",
    i.custom_brand AS "Brand:Data:130",
    COALESCE(
        (SELECT SUM(b.actual_qty)
         FROM `tabBin` b
         WHERE b.item_code = i.item_code
           AND b.warehouse = "Stores - AL"), 0
    ) AS "Cases On Hand:Int:130",
    (
        SELECT MIN(il.expiry_date)
        FROM `tabItem Lot` il
        WHERE il.item_code = i.item_code
          AND (il.expiry_date IS NULL OR il.expiry_date >= CURDATE())
    ) AS "Nearest Expiry:Date:120",
    i.custom_price_per_item AS "Price/Item:Currency:120"
FROM `tabItem` i
WHERE i.disabled = 0
  AND i.is_stock_item = 1
ORDER BY i.item_name'''
rpt.flags.ignore_permissions = True
rpt.save(ignore_permissions=True)
frappe.db.commit()
print("Inventory Manager updated with Nearest Expiry column")

# ── 3. Add a Menu Item shortcut for Item Lot ──────────────────────────────────
# (Optional workspace shortcut — skip if it fails)
try:
    if not frappe.db.exists("Workspace Shortcut", {"label": "Item Lots"}):
        shortcut = frappe.get_doc({
            "doctype": "Workspace Shortcut",
            "label": "Item Lots",
            "type": "DocType",
            "link_to": "Item Lot",
        })
        shortcut.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Added Item Lots workspace shortcut")
except Exception as e:
    print("Shortcut skipped: %s" % str(e)[:60])

print("DONE")
"""

script_b64 = base64.b64encode(remote_script.encode()).decode()

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/itemlots.py'" % script_b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/itemlots.py'",
    ]}, TimeoutSeconds=120)
cid = resp["Command"]["CommandId"]
print("CommandId: %s" % cid)
time.sleep(20)
for _ in range(15):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status: %s" % r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:500])
        break
    print("  %s..." % r["Status"]); time.sleep(10)
