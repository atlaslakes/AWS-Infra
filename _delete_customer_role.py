import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# Check if any users are assigned this profile first
users_on_profile = frappe.get_all("User",
    filters={"role_profile_name": "Customer"},
    fields=["name"])

if users_on_profile:
    print("WARNING: These users are on the Customer profile:", [u["name"] for u in users_on_profile])
    print("Unassigning them first...")
    for u in users_on_profile:
        frappe.db.set_value("User", u["name"], "role_profile_name", "")
    frappe.db.commit()

frappe.delete_doc("Role Profile", "Customer", force=True, ignore_permissions=True)
frappe.db.commit()
print("Customer role profile deleted.")

# Confirm remaining profiles
profiles = frappe.get_all("Role Profile", fields=["name"], order_by="name")
print("Remaining profiles:", [p["name"] for p in profiles])
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/delcustrole.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/delcustrole.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(6):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:400])
        break
    time.sleep(5)
