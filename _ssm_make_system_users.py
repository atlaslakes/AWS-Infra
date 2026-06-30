import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

email = "karavanimports@atlaslakes.com"

# Check what desk_access roles exist
desk_roles = frappe.db.sql(
    "SELECT name FROM `tabRole` WHERE desk_access=1 AND name != 'Administrator' LIMIT 10",
    as_dict=True
)
print("Desk-access roles available:", [r["name"] for r in desk_roles])

# Check if user has any role profiles
user = frappe.get_doc("User", email)
print(f"role_profile_name: {user.role_profile_name}")

# Insert the "System Manager" role directly into tabHasRole
existing = frappe.db.get_value("Has Role", {"parent": email, "role": "System Manager"}, "name")
if not existing:
    frappe.db.sql(
        "INSERT INTO `tabHas Role` (name, creation, modified, modified_by, owner, docstatus, idx, role, parent, parenttype, parentfield) "
        "VALUES (%s, NOW(), NOW(), 'Administrator', 'Administrator', 0, 1, 'System Manager', %s, 'User', 'roles')",
        (frappe.generate_hash(length=10), email)
    )
    print("Inserted System Manager role into tabHas Role")
else:
    print("System Manager role already in tabHas Role")

# Now directly set user_type in the DB
frappe.db.sql("UPDATE `tabUser` SET user_type='System User' WHERE name=%s", (email,))
frappe.db.commit()

# Verify
result = frappe.db.sql("SELECT user_type FROM `tabUser` WHERE name=%s", (email,), as_dict=True)
print(f"DB user_type now: {result[0]['user_type'] if result else 'NOT FOUND'}")

roles_check = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s", (email,), as_dict=True)
print(f"Roles in DB: {[r['role'] for r in roles_check]}")
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/make_sys_user.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/make_sys_user.py'",
]

resp = ssm.send_command(
    InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": commands}, Comment="make karavanimports system user", TimeoutSeconds=60,
)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(15)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print("OUT:", r.get("StandardOutputContent", "")[:800])
        if r.get("StandardErrorContent"):
            print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}...")
    time.sleep(10)
