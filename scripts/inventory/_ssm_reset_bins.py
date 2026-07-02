import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# Cancel and delete all submitted stock reconciliations from today
recons = frappe.db.sql(
    "SELECT name, docstatus FROM `tabStock Reconciliation` WHERE DATE(posting_date)='2026-06-26'",
    as_dict=True
)
for r in recons:
    try:
        frappe.db.set_value("Stock Reconciliation", r['name'], "docstatus", 2)
        frappe.delete_doc("Stock Reconciliation", r['name'], force=True, ignore_permissions=True, delete_permanently=True)
        print(f"Deleted: {r['name']}")
    except Exception as e:
        print(f"ERR {r['name']}: {e}")

# Delete orphaned SLEs and GL entries
frappe.db.sql("DELETE FROM `tabStock Ledger Entry` WHERE voucher_type='Stock Reconciliation' AND DATE(posting_date)='2026-06-26'")
frappe.db.sql("DELETE FROM `tabGL Entry` WHERE voucher_type='Stock Reconciliation' AND DATE(posting_date)='2026-06-26'")
print("Cleaned SLEs and GL entries")

# Reset all bins to 0
frappe.db.sql("UPDATE `tabBin` SET actual_qty=0, stock_value=0, valuation_rate=0, reserved_qty=0, ordered_qty=0, indented_qty=0, planned_qty=0")
print("Reset all bins to 0")

frappe.db.commit()
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/reset.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/reset.py'",
]

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
                        Parameters={"commands": commands}, Comment="reset bins", TimeoutSeconds=60)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(15)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", "")[:2000])
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
