import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

# All non-disabled roles
roles = frappe.get_all("Role",
    fields=["name","disabled","is_custom"],
    order_by="is_custom desc, name")

print(f"Total roles: {len(roles)}")
print()

for r in roles:
    if r["disabled"]:
        continue

    # Custom DocPerm overrides
    custom = frappe.get_all("Custom DocPerm",
        filters={"role": r["name"]},
        fields=["parent","read","write","create","delete","submit","cancel","report","export","import","print","email"],
        order_by="parent")

    # Built-in DocPerm
    builtin = frappe.db.sql(
        "SELECT parent,`read`,`write`,`create`,`delete`,`submit`,`cancel`,`report`,`export` "
        "FROM `tabDocPerm` WHERE role=%s ORDER BY parent",
        r["name"], as_dict=True)

    if not custom and not builtin:
        continue

    tag = "CUSTOM" if r["is_custom"] else "built-in"
    print(f"=== {r['name']} ({tag}) ===")

    def fmt(p, keys=("read","write","create","delete","submit","cancel","report","export","import","print","email")):
        flags = [k for k in keys if p.get(k)]
        return ", ".join(flags) if flags else "-"

    if custom:
        print("  Custom DocPerm:")
        for p in custom:
            print(f"    {p['parent']}: {fmt(p)}")
    if builtin:
        print("  Built-in DocPerm (sample):")
        for p in builtin[:8]:
            print(f"    {p['parent']}: {fmt(p)}")
        if len(builtin) > 8:
            print(f"    ... and {len(builtin)-8} more")
    print()
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/rolescheck.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/rolescheck.py'",
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
