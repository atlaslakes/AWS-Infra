"""
Fixes the Item Lot stock-wiring Server Scripts: submitting/cancelling a Stock Entry
inline inside a Server Script fails (sandbox has no frappe.db.commit), so we now
insert as draft synchronously then submit/cancel via a background job (frappe.enqueue).
Only touches the two Item Lot Server Scripts. Nothing else.
"""
import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote_script = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# After Insert -> create DRAFT Material Receipt, submit it via background job
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
    "    frappe.db.set_value('Item Lot', doc.name, 'stock_entry', se.name)\\n"
    "    frappe.enqueue('frappe.client.submit', queue='short', doc=se.as_dict())\\n"
)

sc1 = frappe.get_doc('Server Script', 'Receive Stock on Item Lot Insert')
sc1.script = insert_script
sc1.flags.ignore_permissions = True
sc1.save(ignore_permissions=True)
print('Updated: Receive Stock on Item Lot Insert')

# Before Delete -> cancel the linked Stock Entry via background job
delete_script = (
    "if doc.stock_entry:\\n"
    "    se = frappe.get_doc('Stock Entry', doc.stock_entry)\\n"
    "    if se.docstatus == 1:\\n"
    "        frappe.enqueue('frappe.client.cancel', queue='short',\\n"
    "                       doctype='Stock Entry', name=doc.stock_entry)\\n"
)

sc2 = frappe.get_doc('Server Script', 'Reverse Stock on Item Lot Delete')
sc2.script = delete_script
sc2.flags.ignore_permissions = True
sc2.save(ignore_permissions=True)
frappe.db.commit()
print('Updated: Reverse Stock on Item Lot Delete')
print('DONE')
"""

script_b64 = base64.b64encode(remote_script.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/fixlotwire.py'" % script_b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fixlotwire.py'",
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
