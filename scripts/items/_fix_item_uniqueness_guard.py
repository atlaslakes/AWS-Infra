import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Use plain string concatenation — guaranteed safe in Frappe's RestrictedPython sandbox
new_script = '''def normalize(value):
    if not value:
        return ""
    parts = (value.strip().lower()).split()
    return " ".join(parts)

name_norm = normalize(doc.item_name)
if not name_norm:
    frappe.throw("Item Name is required")

sku = (doc.get("custom_sku") or "").strip()
invoice_alias = (doc.get("custom_invoice_alias") or "").strip()

name_rows = frappe.db.sql(
    "select name, item_name from `tabItem` where ifnull(disabled,0)=0 and name != %s",
    (doc.name or ""),
    as_dict=True,
)

for row in name_rows:
    if normalize(row.item_name) == name_norm:
        frappe.throw("Item Name already exists as " + row.name + ". Please use a unique name.")

if sku:
    sku_rows = frappe.db.sql(
        "select name from `tabItem` where ifnull(disabled,0)=0 and ifnull(custom_sku,'')=%s and name!=%s limit 1",
        (sku, doc.name or ""),
        as_dict=True,
    )
    if sku_rows:
        frappe.throw("SKU already exists on Item " + sku_rows[0].name + ".")

if invoice_alias:
    alias_rows = frappe.db.sql(
        "select name from `tabItem` where ifnull(disabled,0)=0 and ifnull(custom_invoice_alias,'')=%s and name!=%s limit 1",
        (invoice_alias, doc.name or ""),
        as_dict=True,
    )
    if alias_rows:
        frappe.throw("Invoice Alias already exists on Item " + alias_rows[0].name + ".")
'''

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

sc = frappe.get_doc("Server Script", "Item Uniqueness Guard")
sc.script = \"\"\"%(script)s\"\"\"
sc.flags.ignore_permissions = True
sc.save(ignore_permissions=True)
frappe.db.commit()

# Verify
sc2 = frappe.get_doc("Server Script", "Item Uniqueness Guard")
has_format = ".format(" in sc2.script
print("Saved OK. .format() present:", has_format)
print(sc2.script[:200])
""" % {"script": new_script}

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/fixguard2.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fixguard2.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent",""))
        if r.get("StandardErrorContent","").strip(): print("ERR:", r["StandardErrorContent"][:600])
        break
    time.sleep(5)
