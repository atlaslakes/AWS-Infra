import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# All non-Guest, non-system users
users = frappe.get_all("User",
    filters={"enabled": 1, "user_type": ["!=", "Website User"]},
    fields=["name","full_name","user_type","role_profile_name","last_login"],
    order_by="name")

print(f"Active users: {len(users)}")
print()

for u in users:
    roles = frappe.get_all("Has Role",
        filters={"parent": u["name"], "parenttype": "User"},
        fields=["role"],
        order_by="role")
    role_list = [r["role"] for r in roles]
    print(f"USER: {u['name']}")
    print(f"  Name:         {u['full_name']}")
    print(f"  Type:         {u['user_type']}")
    print(f"  Role Profile: {u['role_profile_name'] or '-'}")
    print(f"  Roles:        {', '.join(role_list) if role_list else '-'}")
    print()

# Also list role profiles
print("=== ROLE PROFILES ===")
profiles = frappe.get_all("Role Profile", fields=["name"])
for p in profiles:
    doc = frappe.get_doc("Role Profile", p["name"])
    roles = [r.role for r in doc.roles]
    print(f"  {p['name']}: {', '.join(roles)}")
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/useroles.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/useroles.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:600])
        break
    time.sleep(5)
