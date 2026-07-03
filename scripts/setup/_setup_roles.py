import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

changes = []

# ── 1. Fill Purchase profile (currently empty) ─────────────────────────────
purchase_roles = [
    "Purchase User",
    "Purchase Manager",
    "Purchase Master Manager",
    "Stock User",
]
p = frappe.get_doc("Role Profile", "Purchase")
existing = [r.role for r in p.roles]
for role in purchase_roles:
    if role not in existing:
        p.append("roles", {"role": role})
p.flags.ignore_permissions = True
p.save(ignore_permissions=True)
frappe.db.commit()
changes.append("Purchase profile filled: " + ", ".join(purchase_roles))

# ── 2. Create Warehouse Staff profile ──────────────────────────────────────
warehouse_roles = [
    "Stock Manager",
    "Stock User",
    "Item Manager",
]
if not frappe.db.exists("Role Profile", "Warehouse Staff"):
    wp = frappe.new_doc("Role Profile")
    wp.role_profile = "Warehouse Staff"
    for role in warehouse_roles:
        wp.append("roles", {"role": role})
    wp.flags.ignore_permissions = True
    wp.insert(ignore_permissions=True)
    frappe.db.commit()
    changes.append("Warehouse Staff profile created: " + ", ".join(warehouse_roles))
else:
    changes.append("Warehouse Staff profile already exists — skipped")

# ── 3. Create Viewer (Read-Only) profile ───────────────────────────────────
viewer_roles = [
    "Auditor",
    "Prepared Report User",
    "Stock User",
    "Sales User",
    "Purchase User",
]
if not frappe.db.exists("Role Profile", "Viewer"):
    vp = frappe.new_doc("Role Profile")
    vp.role_profile = "Viewer"
    for role in viewer_roles:
        vp.append("roles", {"role": role})
    vp.flags.ignore_permissions = True
    vp.insert(ignore_permissions=True)
    frappe.db.commit()
    changes.append("Viewer profile created: " + ", ".join(viewer_roles))
else:
    changes.append("Viewer profile already exists — skipped")

# ── 4. Fix Yura: assign admin role profile ─────────────────────────────────
yura = frappe.get_doc("User", "yura@atlaslakes.com")
if yura.role_profile_name != "admin":
    yura.role_profile_name = "admin"
    yura.flags.ignore_permissions = True
    yura.save(ignore_permissions=True)
    frappe.db.commit()
    changes.append("yura@atlaslakes.com assigned to admin profile")
else:
    changes.append("yura@atlaslakes.com already on admin profile — skipped")

# ── 5. Give Warehouse Staff access to Item Lot doctype ─────────────────────
# Check if custom perm already exists
existing_perm = frappe.db.exists("Custom DocPerm", {
    "parent": "Item Lot",
    "role": "Stock Manager"
})
if not existing_perm:
    for role, perms in [
        ("Stock Manager", {"read":1,"write":1,"create":1,"delete":1,"report":1,"export":1,"print":1}),
        ("Stock User",    {"read":1,"write":1,"create":1,"report":1,"print":1}),
    ]:
        cp = frappe.new_doc("Custom DocPerm")
        cp.parent = "Item Lot"
        cp.parenttype = "DocType"
        cp.parentfield = "permissions"
        cp.role = role
        cp.read = perms.get("read", 0)
        cp.write = perms.get("write", 0)
        cp.create = perms.get("create", 0)
        cp.delete = perms.get("delete", 0)
        cp.report = perms.get("report", 0)
        cp.export = perms.get("export", 0)
        cp.print = perms.get("print", 0)
        cp.flags.ignore_permissions = True
        cp.insert(ignore_permissions=True)
    frappe.db.commit()
    changes.append("Item Lot permissions added for Stock Manager + Stock User")
else:
    changes.append("Item Lot perms for Stock Manager already exist — skipped")

print("Done. Changes applied:")
for c in changes:
    print(" -", c)

# ── Summary: show all profiles ─────────────────────────────────────────────
print()
print("=== Current Role Profiles ===")
profiles = frappe.get_all("Role Profile", fields=["name"], order_by="name")
for p in profiles:
    doc = frappe.get_doc("Role Profile", p["name"])
    roles = [r.role for r in doc.roles]
    print(p["name"] + ": " + (", ".join(roles) if roles else "(empty)"))
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/setuproles.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/setuproles.py'",
    ]}, TimeoutSeconds=40)
cid = resp["Command"]["CommandId"]
time.sleep(14)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:800])
        break
    time.sleep(5)
