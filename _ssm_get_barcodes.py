import boto3, base64, time, json
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe, json
frappe.init(site="karavanimports.com")
frappe.connect()

rows = frappe.db.sql(
    "SELECT parent AS item_code, barcode FROM `tabItem Barcode`",
    as_dict=True
)
print("BARCODES:" + json.dumps([{"item_code": r["item_code"], "barcode": str(r["barcode"])} for r in rows]))
print(f"COUNT:{len(rows)}")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/bc.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/bc.py'",
]

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
                        Parameters={"commands": commands}, Comment="get barcodes", TimeoutSeconds=60)
cmd_id = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        out = r.get("StandardOutputContent", "")
        for line in out.splitlines():
            if line.startswith("BARCODES:"):
                data = json.loads(line[9:])
                with open("_barcodes.json", "w") as f:
                    json.dump(data, f)
                print(f"Saved {len(data)} barcodes to _barcodes.json")
            elif line.startswith("COUNT:"):
                print(line)
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:200])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
