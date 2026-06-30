import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()

# Check tabBin
bin_count = frappe.db.sql("SELECT COUNT(*) FROM `tabBin` WHERE actual_qty > 0")[0][0]
print(f"tabBin rows with actual_qty > 0: {bin_count}")

sample = frappe.db.sql("SELECT item_code, warehouse, actual_qty FROM `tabBin` WHERE actual_qty > 0 LIMIT 5", as_dict=True)
print("\\nSample Bin rows:")
for r in sample:
    print(f"  {r['item_code']:20} | {r['warehouse']:20} | qty={r['actual_qty']}")

# Check SLE
sle_count = frappe.db.sql("SELECT COUNT(*) FROM `tabStock Ledger Entry` WHERE is_cancelled=0")[0][0]
print(f"\\ntabSLE active rows: {sle_count}")

sle_sample = frappe.db.sql(
    "SELECT item_code, warehouse, actual_qty, qty_after_transaction, voucher_type FROM `tabStock Ledger Entry` WHERE is_cancelled=0 LIMIT 5",
    as_dict=True)
print("Sample SLE rows:")
for r in sle_sample:
    print(f"  {r['item_code']:20} | {r['warehouse']:20} | qty={r['actual_qty']} | after={r['qty_after_transaction']}")

# Check what the report query returns for a specific item
item_code = frappe.db.sql("SELECT name FROM `tabItem` WHERE disabled=0 LIMIT 1")[0][0]
result = frappe.db.sql(
    "SELECT SUM(b.actual_qty) FROM `tabBin` b WHERE b.item_code=%s AND b.warehouse='Stores - AL'",
    (item_code,))
print(f"\\nReport subquery for {item_code}: {result[0][0]}")

# Check exact warehouse names in Bin
warehouses = frappe.db.sql("SELECT DISTINCT warehouse FROM `tabBin`", as_list=True)
print(f"\\nWarehouses in tabBin: {[w[0] for w in warehouses]}")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/diagstock.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/diagstock.py'",
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
