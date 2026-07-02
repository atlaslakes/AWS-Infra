import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

frappe.db.sql("SET FOREIGN_KEY_CHECKS=0")

tables = [
    "tabStock Reconciliation Item",
    "tabStock Reconciliation",
    "tabStock Ledger Entry",
    "tabGL Entry",
    "tabBin",
    "tabItem Barcode",
    "tabItem Price",
    "tabUOM Conversion Detail",
    "tabItem Tax",
    "tabItem Supplier",
    "tabItem Customer Detail",
    "tabWebsite Item",
    "tabItem Variant Attribute",
    "tabItem Default",
    "tabItem Reorder",
]
for t in tables:
    try:
        frappe.db.sql(f"DELETE FROM `{t}`")
        print(f"  Cleared: {t}")
    except Exception as e:
        print(f"  Skip {t}: {e}")

count = frappe.db.sql("SELECT COUNT(*) FROM `tabItem`")[0][0]
frappe.db.sql("DELETE FROM `tabItem`")
print(f"Deleted {count} items")

frappe.db.sql("SET FOREIGN_KEY_CHECKS=1")
frappe.db.commit()
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/del.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/del.py'",
]

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
                        Parameters={"commands": commands}, Comment="delete all items", TimeoutSeconds=120)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(20)
for _ in range(12):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent","")[:3000])
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
