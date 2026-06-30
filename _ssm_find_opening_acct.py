import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = b"""
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()

# Find Asset/Liability accounts suitable for opening entry
accts = frappe.db.sql(
    "SELECT name, account_type, root_type FROM `tabAccount` "
    "WHERE company='Atlas Lakes' AND root_type IN ('Asset','Liability') "
    "AND is_group=0 AND disabled=0 "
    "ORDER BY root_type, account_type LIMIT 20",
    as_dict=True)

print("Asset/Liability accounts:")
for a in accts:
    print("  %-50s | type=%-25s | root=%s" % (a['name'], a['account_type'] or '-', a['root_type']))

# Also look for "Temporary Opening"
temp = frappe.db.sql(
    "SELECT name FROM `tabAccount` WHERE name LIKE '%Temporary%' OR name LIKE '%Opening%'",
    as_dict=True)
print("\\nTemporary/Opening accounts:", [a['name'] for a in temp])
"""

b64 = base64.b64encode(py).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/findacct.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/findacct.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
print("CommandId:", cid)
time.sleep(12)
for _ in range(6):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent",""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print(" ", r["Status"]+"..."); time.sleep(8)
