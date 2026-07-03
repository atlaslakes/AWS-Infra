import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

renames = [
    ("6251591112236", "GEN-0084"),
    ("11",            "SPICE-0025"),
    ("111",           "COND-0011"),
    ("55",            "SPICE-0026"),
    ("123",           "SPICE-0027"),
    ("111111",        "SPICE-0028"),
    ("5555",          "SPICE-0029"),
    ("7887",          "SPICE-0030"),
    ("554545",        "SPICE-0031"),
    ("8975",          "SPICE-0032"),
    ("9896",          "SPICE-0033"),
    ("564",           "PASTA-0008"),
]

lines = [
    "import frappe",
    "frappe.init(site='karavanimports.com')",
    "frappe.connect()",
    "frappe.set_user('Administrator')",
    "renames = " + repr(renames),
    "for old, new in renames:",
    "    try:",
    "        frappe.rename_doc('Item', old, new, force=True, merge=False)",
    "        frappe.db.commit()",
    "        print('OK: %s -> %s' % (old, new))",
    "    except Exception as e:",
    "        print('FAIL: %s -> %s | %s' % (old, new, str(e)[:120]))",
]

b64 = base64.b64encode("\n".join(lines).encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/renameitems.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/renameitems.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
time.sleep(16)
for _ in range(10):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:600])
        break
    time.sleep(6)
