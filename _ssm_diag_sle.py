import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()

item = "BEAN-0014"
warehouse = "Stores - AL"

# Check bin
bin_qty = frappe.db.sql(
    "SELECT actual_qty FROM `tabBin` WHERE item_code=%s AND warehouse=%s",
    (item, warehouse))
print(f"tabBin actual_qty: {bin_qty}")

# Check SLEs
sles = frappe.db.sql(
    "SELECT name, actual_qty, qty_after_transaction, posting_date, posting_time, is_cancelled, docstatus, stock_uom "
    "FROM `tabStock Ledger Entry` WHERE item_code=%s AND warehouse=%s ORDER BY posting_date DESC, posting_time DESC LIMIT 5",
    (item, warehouse), as_dict=True)
print(f"\\nSLEs for {item}:")
for s in sles:
    print(f"  name={s['name'][:8]} qty={s['actual_qty']} after={s['qty_after_transaction']} "
          f"date={s['posting_date']} time={s['posting_time']} cancelled={s['is_cancelled']} "
          f"docstatus={s['docstatus']} uom={s['stock_uom']}")

# Check item stock_uom
item_uom = frappe.db.get_value("Item", item, ["stock_uom", "is_stock_item"], as_dict=True)
print(f"\\nItem stock_uom: {item_uom.stock_uom}, is_stock_item: {item_uom.is_stock_item}")

# Try get_stock_balance
from erpnext.stock.stock_ledger import get_previous_sle
prev = get_previous_sle({
    "item_code": item,
    "warehouse": warehouse,
    "posting_date": frappe.utils.today(),
    "posting_time": "23:59:59",
})
print(f"\\nget_previous_sle result: {prev}")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/diagsle.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/diagsle.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
print(f"CommandId: {cid}")
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:500])
        break
    print(f"  {r['Status']}..."); time.sleep(8)
