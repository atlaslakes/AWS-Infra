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

# Roles to assign for full access (covers Warehouse + all stock/inventory ops)
ROLES = [
    "System Manager",
    "Stock Manager",
    "Stock User",
    "Item Manager",
    "Accounts Manager",
    "Accounts User",
    "Sales Manager",
    "Purchase Manager",
]

existing = {r['role'] for r in frappe.db.sql(
    "SELECT role FROM `tabHas Role` WHERE parent=%s", (email,), as_dict=True
)}
print(f"Existing roles: {existing}")

added = []
for role in ROLES:
    if role not in existing:
        frappe.db.sql(
            "INSERT INTO `tabHas Role` (name, creation, modified, modified_by, owner, "
            "docstatus, idx, role, parent, parenttype, parentfield) "
            "VALUES (%s, NOW(), NOW(), 'Administrator', 'Administrator', 0, 1, %s, %s, 'User', 'roles')",
            (frappe.generate_hash(length=10), role, email)
        )
        added.append(role)

# Ensure user_type stays System User
frappe.db.sql("UPDATE `tabUser` SET user_type='System User' WHERE name=%s", (email,))
frappe.db.commit()

# Clear all caches
try:
    frappe.clear_cache(user=email)
except Exception as e:
    print(f"cache clear: {e}")

print(f"Added roles: {added}")
final = [r['role'] for r in frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s", (email,), as_dict=True)]
print(f"Final roles: {final}")
print(f"user_type: {frappe.db.get_value('User', email, 'user_type')}")
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/fix_perms.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fix_perms.py'",
]

resp = ssm.send_command(
    InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": commands}, Comment="fix user roles and perms", TimeoutSeconds=60,
)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(15)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print("OUT:", r.get("StandardOutputContent", "")[:1500])
        if r.get("StandardErrorContent"):
            print("ERR:", r["StandardErrorContent"][:400])
        break
    print(f"  {r['Status']}...")
    time.sleep(10)
