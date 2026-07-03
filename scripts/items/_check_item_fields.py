import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = (
    "import frappe\n"
    "frappe.init(site='karavanimports.com')\n"
    "frappe.connect()\n"
    "frappe.set_user('Administrator')\n"
    "fields = frappe.db.sql(\"DESCRIBE `tabItem`\", as_dict=True)\n"
    "custom = [f['Field'] for f in fields if any(k in f['Field'].lower() for k in ['brand','sku','upc','barcode','size','case','alias','invoice'])]\n"
    "for f in custom: print(f)\n"
)

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/chkfields.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/chkfields.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(10)
for _ in range(6):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:300])
        break
    time.sleep(5)
