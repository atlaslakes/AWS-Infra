import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# All stock reconciliations from today
recons = frappe.db.sql(
    "SELECT name, docstatus FROM `tabStock Reconciliation` WHERE DATE(posting_date) = '2026-06-26' ORDER BY name",
    as_dict=True
)
print(f"Found {len(recons)} reconciliation(s) from 2026-06-26")

for rec in recons:
    name = rec["name"]
    status = rec["docstatus"]
    print(f"\\n  {name} (docstatus={status})")

    try:
        # Force cancel via DB if still submitted
        if status == 1:
            frappe.db.set_value("Stock Reconciliation", name, "docstatus", 2)
            frappe.db.commit()
            print(f"    Force-cancelled via DB")

        # Force delete including all linked children
        frappe.delete_doc("Stock Reconciliation", name,
                          force=True, ignore_permissions=True, delete_permanently=True)
        print(f"    Deleted")
    except Exception as e:
        print(f"    ERR: {str(e)[:200]}")

# Also clean up any orphaned Stock Ledger Entries / GL Entries from these recons
try:
    frappe.db.sql(
        "DELETE FROM `tabStock Ledger Entry` WHERE voucher_type='Stock Reconciliation' AND DATE(posting_date)='2026-06-26'"
    )
    frappe.db.sql(
        "DELETE FROM `tabGL Entry` WHERE voucher_type='Stock Reconciliation' AND DATE(posting_date)='2026-06-26'"
    )
    frappe.db.commit()
    print("\\nCleaned orphaned SLE/GL entries")
except Exception as e:
    print(f"\\nSLE/GL cleanup ERR: {str(e)[:200]}")

# Recalculate bin quantities (reset to 0 since no stock entries remain)
try:
    frappe.db.sql("UPDATE `tabBin` SET actual_qty=0, stock_value=0, valuation_rate=0")
    frappe.db.commit()
    print("Reset all Bin quantities to 0")
except Exception as e:
    print(f"Bin reset ERR: {str(e)[:200]}")

frappe.db.commit()
print("\\nDONE")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/rollback_recon.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/rollback_recon.py'",
]

resp = ssm.send_command(
    InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": commands}, Comment="rollback stock recons", TimeoutSeconds=180,
)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(25)
for _ in range(12):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print("OUT:", r.get("StandardOutputContent", "")[:2000])
        if r.get("StandardErrorContent"):
            print("ERR:", r["StandardErrorContent"][:400])
        break
    print(f"  {r['Status']}...")
    time.sleep(10)
