import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# Delete draft recon that failed
for name in frappe.db.sql("SELECT name FROM `tabStock Reconciliation` WHERE docstatus=0", as_list=True):
    try:
        frappe.delete_doc("Stock Reconciliation", name[0], force=True, ignore_permissions=True)
        print(f"Deleted draft: {name[0]}")
    except Exception as e:
        print(f"ERR deleting {name[0]}: {e}")

# Clear all prepared/cached reports for Inventory Manager
frappe.db.sql("DELETE FROM `tabPrepared Report` WHERE report_name='Inventory Manager'")
print("Cleared prepared reports for Inventory Manager")

# Clear all report cache keys
frappe.cache().delete_keys("report_*")
frappe.cache().delete_keys("query_report_*")
frappe.clear_cache()
print("Cleared all report cache")

# Verify current Bin values for sample items
print("\\n=== Current Bin (cases) ===")
bins = frappe.db.sql(
    "SELECT b.item_code, b.actual_qty, i.item_name "
    "FROM `tabBin` b JOIN `tabItem` i ON i.name=b.item_code "
    "WHERE b.actual_qty > 0 ORDER BY b.item_code LIMIT 20",
    as_dict=True
)
for b in bins:
    print(f"  {b['item_code']:14} {b['actual_qty']:6.1f} cases  {b['item_name'][:40]}")

frappe.db.commit()
print("\\nDONE")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/clear_cache.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/clear_cache.py'",
]

resp = ssm.send_command(
    InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": commands}, Comment="clear report cache", TimeoutSeconds=60,
)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(15)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print("OUT:", r.get("StandardOutputContent", "")[:2000])
        if r.get("StandardErrorContent"):
            print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}...")
    time.sleep(10)
