import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

WAREHOUSE = "Stores - AL"

# 1. Re-enable stock on all items
frappe.db.sql("UPDATE `tabItem` SET is_stock_item=1 WHERE is_stock_item=0")
count = frappe.db.sql("SELECT COUNT(*) FROM `tabItem` WHERE is_stock_item=1")[0][0]
print(f"is_stock_item=1 on {count} items")

# 2. Re-enable stock accounting
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
print("allow_negative_stock = 1 (safety net)")

frappe.db.commit()

# 3. Load opening stock directly into tabBin from cases_on_hand
items = frappe.db.sql(
    "SELECT name, cases_on_hand FROM `tabItem` WHERE disabled=0 AND COALESCE(cases_on_hand,0)>0",
    as_dict=True)

print(f"\\nLoading opening stock for {len(items)} items into {WAREHOUSE}...")

inserted = updated = 0
for item in items:
    qty = int(item["cases_on_hand"])
    existing = frappe.db.get_value("Bin", {"item_code": item["name"], "warehouse": WAREHOUSE}, "name")
    if existing:
        frappe.db.sql(
            "UPDATE `tabBin` SET actual_qty=%s, projected_qty=%s WHERE name=%s",
            (qty, qty, existing))
        updated += 1
    else:
        import uuid
        bin_name = frappe.generate_hash(length=10)
        frappe.db.sql(
            "INSERT INTO `tabBin` (name, item_code, warehouse, actual_qty, projected_qty, stock_uom, creation, modified, owner, modified_by) "
            "VALUES (%s, %s, %s, %s, %s, 'Nos', NOW(), NOW(), 'Administrator', 'Administrator')",
            (bin_name, item["name"], WAREHOUSE, qty, qty))
        inserted += 1

frappe.db.commit()
print(f"  Inserted: {inserted}  Updated: {updated}")
print("\\nDONE")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/enablestock.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/enablestock.py'",
    ]}, TimeoutSeconds=120)
cid = resp["Command"]["CommandId"]
print(f"CommandId: {cid}")
time.sleep(20)
for _ in range(15):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:500])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
