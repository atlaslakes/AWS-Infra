"""
Removes the cases_on_hand Custom Field from Item.

Custom Fields get serialized into every Item REST response, which
isn't wanted. Stock is now shown directly from the core, non-custom
Bin.actual_qty, computed live in the Inventory Manager report (see
scripts/inventory/_update_inventory_manager_query.py) instead of being
mirrored into a separate field on Item.

Deletion must run via SSM/Administrator (not a REST call from another
user) -- this Custom Field is Administrator-owned, and Frappe blocks
deleting an Administrator-owned Custom Field through any other account.

Run:
    python _remove_cases_on_hand_field.py
"""

import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

names = frappe.get_all("Custom Field", filters={"dt": "Item", "fieldname": "cases_on_hand"}, pluck="name")
print("Found:", names)
for n in names:
    frappe.delete_doc("Custom Field", n, force=True, ignore_permissions=True)
    print(f"Deleted: {n}")
frappe.db.commit()
print("Done.")
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/rm_coh.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/rm_coh.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:500])
        break
    time.sleep(6)
