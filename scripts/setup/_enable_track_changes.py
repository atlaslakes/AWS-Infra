import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# 1. Enable track_changes on ALL existing doctypes
result = frappe.db.sql(
    "UPDATE `tabDocType` SET track_changes = 1 WHERE track_changes = 0 OR track_changes IS NULL"
)
frappe.db.commit()

total = frappe.db.sql("SELECT COUNT(*) FROM `tabDocType` WHERE track_changes = 1")[0][0]
print(f"Track Changes enabled on {total} doctypes.")

# 2. Create Server Script to auto-enable on any future DocType
script_name = "Auto Enable Track Changes"
if frappe.db.exists("Server Script", script_name):
    frappe.delete_doc("Server Script", script_name, force=True, ignore_permissions=True)
    frappe.db.commit()

sc = frappe.new_doc("Server Script")
sc.name = script_name
sc.script_type = "DocType Event"
sc.reference_doctype = "DocType"
sc.doctype_event = "After Insert"
sc.disabled = 0
sc.script = '''if not doc.track_changes:
    frappe.db.set_value("DocType", doc.name, "track_changes", 1)
'''
sc.flags.ignore_permissions = True
sc.insert(ignore_permissions=True)
frappe.db.commit()
print("Server Script created: new DocTypes will auto-enable track_changes on insert.")

# 3. Clear cache so changes take effect
frappe.clear_cache()
print("Cache cleared.")
print("Done.")
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/trackchanges.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/trackchanges.py'",
    ]}, TimeoutSeconds=40)
cid = resp["Command"]["CommandId"]
time.sleep(14)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:600])
        break
    time.sleep(5)
