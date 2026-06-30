import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote_script = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

rpt = frappe.get_doc("Report", "Inventory Manager")
rpt.query = '''SELECT
    i.item_code   AS "Item ID:Link/Item:130",
    i.item_name   AS "Description:Data:250",
    i.brand       AS "Brand:Data:130",
    COALESCE(
        (SELECT SUM(b.actual_qty)
         FROM `tabBin` b
         WHERE b.item_code = i.item_code
           AND b.warehouse = "Stores - AL"), 0
    ) AS "Cases On Hand:Int:130",
    (
        SELECT MIN(il.expiry_date)
        FROM `tabItem Lot` il
        WHERE il.item_code = i.item_code
          AND (il.expiry_date IS NULL OR il.expiry_date >= CURDATE())
    ) AS "Nearest Expiry:Date:120",
    i.custom_price AS "Price/Item:Currency:120"
FROM `tabItem` i
WHERE i.disabled = 0
  AND i.is_stock_item = 1
ORDER BY i.item_name'''
rpt.flags.ignore_permissions = True
rpt.save(ignore_permissions=True)
frappe.db.commit()
print("Inventory Manager SQL fixed")

# Quick sanity check
rows = frappe.db.sql(rpt.query, as_dict=True)
print("Row count: %d" % len(rows))
if rows:
    r = rows[0]
    print("Sample: %s | %s | qty=%s | expiry=%s | price=%s" % (
        r.get("Item ID:Link/Item:130") or r.get("item_id","?"),
        r.get("Description:Data:250", "?")[:30],
        r.get("Cases On Hand:Int:130","?"),
        r.get("Nearest Expiry:Date:120","none"),
        r.get("Price/Item:Currency:120","?"),
    ))
print("DONE")
"""

script_b64 = base64.b64encode(remote_script.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/fixrpt2.py'" % script_b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fixrpt2.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
print("CommandId: %s" % cid)
time.sleep(15)
for _ in range(10):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status: %s" % r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print("  %s..." % r["Status"]); time.sleep(8)
