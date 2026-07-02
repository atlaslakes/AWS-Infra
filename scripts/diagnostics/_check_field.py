import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()

# Check custom field definition
cf = frappe.db.sql("SELECT name, fieldname, fieldtype, dt FROM `tabCustom Field` WHERE dt='Item' AND fieldname='cases_on_hand'", as_dict=True)
print("Custom field def:", cf)

# Check actual DB column
cols = frappe.db.sql("SHOW COLUMNS FROM `tabItem` LIKE 'cases_on_hand'", as_dict=True)
print("DB column:", cols)

# Check actual values in DB
rows = frappe.db.sql("SELECT name, cases_on_hand FROM `tabItem` WHERE cases_on_hand > 0 LIMIT 5", as_dict=True)
print(f"Items with cases_on_hand > 0: {len(rows)} (sample):")
for r in rows:
    print(f"  {r['name']}: {r['cases_on_hand']}")

# Check what the report script reads
rpt = frappe.db.get_value("Report", "Inventory Manager", "script")
# find the cases_on_hand line
for line in (rpt or "").splitlines():
    if "cases" in line.lower():
        print("Report line:", line.strip())
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands":[
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/chk.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/chk.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
time.sleep(15)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"):
        print(r["Status"])
        print(r.get("StandardOutputContent",""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:200])
        break
    time.sleep(8)
