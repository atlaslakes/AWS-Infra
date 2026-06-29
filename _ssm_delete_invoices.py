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
    "tabSales Invoice Item",
    "tabSales Invoice Tax",
    "tabSales Invoice Payment",
    "tabSales Invoice",
    "tabPurchase Invoice Item",
    "tabPurchase Invoice Tax",
    "tabPurchase Invoice",
    "tabPayment Entry Reference",
    "tabPayment Entry",
    "tabGL Entry",
    "tabPayment Ledger Entry",
]

for t in tables:
    try:
        count = frappe.db.sql(f"SELECT COUNT(*) FROM `{t}`")[0][0]
        frappe.db.sql(f"DELETE FROM `{t}`")
        print(f"  Cleared {count:4} rows: {t}")
    except Exception as e:
        print(f"  Skip {t}: {e}")

frappe.db.sql("SET FOREIGN_KEY_CHECKS=1")
frappe.db.commit()
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/delinv.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/delinv.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
print(f"CommandId: {cid}")
time.sleep(15)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent",""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:200])
        break
    print(f"  {r['Status']}..."); time.sleep(8)
