import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote_script = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

rows = frappe.get_all("Server Script", filters={"reference_doctype": "Stock Entry"},
                       fields=["name", "script_type", "doctype_event", "disabled"])
print("Server Scripts on Stock Entry:", rows)

names = frappe.get_all("Server Script", fields=["name"])
print("\\nAll Server Script names:")
for n in names:
    print(" -", n["name"])

for n in names:
    if "expiry" in n["name"].lower() or "lot" in n["name"].lower() or "karavan" in n["name"].lower():
        sc = frappe.get_doc("Server Script", n["name"])
        print("\\n==== %s ====" % n["name"])
        print("reference_doctype:", sc.reference_doctype, "event:", sc.doctype_event, "disabled:", sc.disabled)
        print(sc.script)
"""

script_b64 = base64.b64encode(remote_script.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'rm -f /tmp/inspect.py'",
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/inspectsc.py'" % script_b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/inspectsc.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(10)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:1000])
        break
    time.sleep(5)
