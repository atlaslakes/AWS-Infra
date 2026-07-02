"""
Wires Item Lot lifecycle to stock (Option C):
- Adds a 'stock_entry' tracking field on Item Lot
- After Insert  -> creates + submits a Material Receipt Stock Entry for cases_received
- Before Delete -> cancels the linked Stock Entry (reverses the stock) before the lot is removed
Only touches the Item Lot doctype and its two Server Scripts. Nothing else.
"""
import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote_script = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# 1. Add a read-only 'stock_entry' field on Item Lot for traceability
dt = frappe.get_doc("DocType", "Item Lot")
existing = [f.fieldname for f in dt.fields]
if "stock_entry" not in existing:
    dt.append("fields", {
        "fieldname": "stock_entry",
        "fieldtype": "Link",
        "label": "Stock Entry",
        "options": "Stock Entry",
        "read_only": 1,
        "insert_after": "notes",
    })
    dt.flags.ignore_permissions = True
    dt.save(ignore_permissions=True)
    frappe.db.commit()
    print("Added stock_entry field to Item Lot")
else:
    print("stock_entry field already exists")

# 2. After Insert -> receive stock via Material Receipt
if frappe.db.exists("Server Script", "Receive Stock on Item Lot Insert"):
    frappe.delete_doc("Server Script", "Receive Stock on Item Lot Insert", force=True, ignore_permissions=True)

insert_script = (
    "if doc.cases_received and doc.cases_received > 0:\\n"
    "    se = frappe.new_doc('Stock Entry')\\n"
    "    se.stock_entry_type = 'Material Receipt'\\n"
    "    se.company = 'Atlas Lakes'\\n"
    "    se.append('items', {\\n"
    "        'item_code': doc.item_code,\\n"
    "        'qty': doc.cases_received,\\n"
    "        't_warehouse': 'Stores - AL',\\n"
    "        'basic_rate': 1,\\n"
    "    })\\n"
    "    se.flags.ignore_permissions = True\\n"
    "    se.insert(ignore_permissions=True)\\n"
    "    se.submit()\\n"
    "    frappe.db.set_value('Item Lot', doc.name, 'stock_entry', se.name)\\n"
)

sc1 = frappe.get_doc({
    "doctype": "Server Script",
    "name": "Receive Stock on Item Lot Insert",
    "script_type": "DocType Event",
    "reference_doctype": "Item Lot",
    "doctype_event": "After Insert",
    "script": insert_script,
    "disabled": 0,
})
sc1.flags.ignore_permissions = True
sc1.insert(ignore_permissions=True)
print("Server Script created: Receive Stock on Item Lot Insert")

# 3. Before Delete -> cancel the linked Stock Entry to reverse the stock
if frappe.db.exists("Server Script", "Reverse Stock on Item Lot Delete"):
    frappe.delete_doc("Server Script", "Reverse Stock on Item Lot Delete", force=True, ignore_permissions=True)

delete_script = (
    "if doc.stock_entry:\\n"
    "    se = frappe.get_doc('Stock Entry', doc.stock_entry)\\n"
    "    if se.docstatus == 1:\\n"
    "        se.flags.ignore_permissions = True\\n"
    "        se.cancel()\\n"
)

sc2 = frappe.get_doc({
    "doctype": "Server Script",
    "name": "Reverse Stock on Item Lot Delete",
    "script_type": "DocType Event",
    "reference_doctype": "Item Lot",
    "doctype_event": "Before Delete",
    "script": delete_script,
    "disabled": 0,
})
sc2.flags.ignore_permissions = True
sc2.insert(ignore_permissions=True)
frappe.db.commit()
print("Server Script created: Reverse Stock on Item Lot Delete")
print("DONE")
"""

script_b64 = base64.b64encode(remote_script.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/wirelot.py'" % script_b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/wirelot.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
print("CommandId: %s" % cid)
time.sleep(15)
for _ in range(10):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status: %s" % r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:500])
        break
    print("  %s..." % r["Status"]); time.sleep(8)
