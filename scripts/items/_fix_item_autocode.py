import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

client_script = (
    'frappe.ui.form.on("Item", {\n'
    '    setup: function(frm) {\n'
    '        if (frm.doc.__islocal && !frm.doc.item_code) {\n'
    '            frm.set_value("item_code", "AUTO");\n'
    '            frm.set_value("item_name", "");\n'
    '        }\n'
    '    },\n'
    '    item_group: function(frm) {\n'
    '        var code = frm.doc.item_code;\n'
    '        if (frm.doc.__islocal && (!code || code === "AUTO" || /^[0-9]+$/.test(code))) {\n'
    '            frm.set_value("item_code", "AUTO");\n'
    '            frm.set_value("item_name", frm.doc.item_name || "");\n'
    '        }\n'
    '    }\n'
    '});'
)

setup = "\n".join([
    "import frappe",
    "frappe.init(site='karavanimports.com')",
    "frappe.connect()",
    "frappe.set_user('Administrator')",
    "cs_name = 'Item Auto Code Preview'",
    "if frappe.db.exists('Client Script', cs_name):",
    "    frappe.delete_doc('Client Script', cs_name, force=True, ignore_permissions=True)",
    "    frappe.db.commit()",
    "cs = frappe.new_doc('Client Script')",
    "cs.name = cs_name",
    "cs.dt = 'Item'",
    "cs.script_type = 'Form'",
    "cs.enabled = 1",
    "cs.script = " + repr(client_script),
    "cs.flags.ignore_permissions = True",
    "cs.insert(ignore_permissions=True)",
    "frappe.db.commit()",
    "frappe.clear_cache(doctype='Item')",
    "print('Done.')",
])

b64 = base64.b64encode(setup.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/fixcs.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fixcs.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(6):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent","").strip():
            print("ERR:", r["StandardErrorContent"][:400])
        break
    time.sleep(5)
