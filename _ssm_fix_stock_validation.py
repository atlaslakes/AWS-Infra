import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# 1. Enable negative stock so invoices don't block on zero bin qty
frappe.db.set_value("Stock Settings", "Stock Settings", "allow_negative_stock", 1)
print("allow_negative_stock = 1")

# 2. Mark all items as non-stock items (we track stock via cases_on_hand custom field)
count = frappe.db.sql("UPDATE `tabItem` SET is_stock_item=0 WHERE is_stock_item=1")
result = frappe.db.sql("SELECT COUNT(*) FROM `tabItem` WHERE is_stock_item=0")[0][0]
print(f"is_stock_item=0 on {result} items")

# 3. Disable 'Update Stock' default on Sales Invoice (Stock Settings)
try:
    frappe.db.set_value("Stock Settings", "Stock Settings", "auto_accounting_for_stock", 0)
    print("auto_accounting_for_stock = 0")
except Exception as e:
    print(f"auto_accounting_for_stock skip: {e}")

frappe.db.commit()
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/fixstock.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fixstock.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
print(f"CommandId: {cid}")
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}..."); time.sleep(8)
