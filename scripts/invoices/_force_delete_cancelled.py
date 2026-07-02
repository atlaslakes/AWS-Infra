import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

names = ["ACC-SINV-2026-00029", "ACC-SINV-2026-00030", "ACC-SINV-2026-00031"]
for name in names:
    try:
        frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)
        frappe.db.commit()
        print("Deleted:", name)
    except Exception as e:
        print("FAIL:", name, str(e)[:120])
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/delinv.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/delinv.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(10)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent",""))
        if r.get("StandardErrorContent","").strip(): print("ERR:", r["StandardErrorContent"][:400])
        break
    time.sleep(5)
