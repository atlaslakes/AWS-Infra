import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# When was Item Uniqueness Guard last modified?
sc = frappe.get_doc("Server Script", "Item Uniqueness Guard")
print("Item Uniqueness Guard:")
print("  created:  ", sc.creation)
print("  modified: ", sc.modified)
print("  event:    ", sc.doctype_event)
print("  disabled: ", sc.disabled)

# Recent error log entries related to Item / format
print("\\nRecent Error Log (last 10):")
errors = frappe.get_all("Error Log",
    fields=["name", "method", "error", "creation"],
    order_by="creation desc",
    limit=10)
for e in errors:
    print(f"  [{e['creation']}] {e.get('method','')[:60]}")
    print(f"    {str(e.get('error',''))[:120]}")

# All server scripts modified today
print("\\nServer Scripts modified on/after 2026-06-30:")
scripts = frappe.get_all("Server Script",
    fields=["name","modified","doctype_event","reference_doctype","disabled"],
    filters=[["modified",">=","2026-06-30"]],
    order_by="modified desc")
for sc in scripts:
    print(f"  {sc['modified']} | {sc['name']} | {sc['reference_doctype']} | {sc['doctype_event']} | disabled={sc['disabled']}")
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/diagchg.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/diagchg.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent",""))
        if r.get("StandardErrorContent","").strip(): print("ERR:", r["StandardErrorContent"][:400])
        break
    time.sleep(5)
