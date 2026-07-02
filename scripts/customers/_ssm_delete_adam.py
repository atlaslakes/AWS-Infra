import boto3, base64, time, urllib3
urllib3.disable_warnings()
ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Python script to force-delete adam and all linked records inside frappe
py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

CUSTOMER = "adam"

# Force-delete linked Sales Invoices (GL entries included)
invoices = frappe.get_all("Sales Invoice", filters={"customer": CUSTOMER}, fields=["name","docstatus"])
for inv in invoices:
    print("Deleting invoice:", inv["name"], "docstatus:", inv["docstatus"])
    try:
        frappe.delete_doc("Sales Invoice", inv["name"], force=True, ignore_permissions=True, delete_permanently=True)
        print("  deleted")
    except Exception as e:
        print("  ERR:", str(e)[:150])

# Sales Orders
for doc in frappe.get_all("Sales Order", filters={"customer": CUSTOMER}, fields=["name"]):
    try:
        frappe.delete_doc("Sales Order", doc["name"], force=True, ignore_permissions=True, delete_permanently=True)
        print("Deleted SO:", doc["name"])
    except Exception as e:
        print("ERR SO:", str(e)[:150])

# Delivery Notes
for doc in frappe.get_all("Delivery Note", filters={"customer": CUSTOMER}, fields=["name"]):
    try:
        frappe.delete_doc("Delivery Note", doc["name"], force=True, ignore_permissions=True, delete_permanently=True)
        print("Deleted DN:", doc["name"])
    except Exception as e:
        print("ERR DN:", str(e)[:150])

# Communications referencing adam
for doc in frappe.get_all("Communication", filters={"reference_name": CUSTOMER}, fields=["name"]):
    try:
        frappe.delete_doc("Communication", doc["name"], force=True, ignore_permissions=True)
        print("Deleted Comm:", doc["name"])
    except Exception as e:
        print("ERR Comm:", str(e)[:100])

# Contact adam-adam
for doc in frappe.get_all("Contact", filters=[["link_name","=",CUSTOMER]], fields=["name"]):
    try:
        frappe.delete_doc("Contact", doc["name"], force=True, ignore_permissions=True, delete_permanently=True)
        print("Deleted Contact:", doc["name"])
    except Exception as e:
        print("ERR Contact:", str(e)[:150])

for doc in frappe.get_all("Contact", filters=[["name","like","%adam%"]], fields=["name"]):
    try:
        frappe.delete_doc("Contact", doc["name"], force=True, ignore_permissions=True, delete_permanently=True)
        print("Deleted Contact:", doc["name"])
    except Exception as e:
        print("ERR Contact:", str(e)[:150])

# Customer
try:
    frappe.delete_doc("Customer", CUSTOMER, force=True, ignore_permissions=True, delete_permanently=True)
    print("Deleted Customer:", CUSTOMER)
except Exception as e:
    print("ERR Customer:", str(e)[:200])

frappe.db.commit()
print("DONE - committed")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/del_adam.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/del_adam.py'",
]

resp = ssm.send_command(
    InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": commands}, Comment="delete adam", TimeoutSeconds=120,
)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(20)
for _ in range(10):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"):
        print(f"Status: {r['Status']}")
        print("OUT:", r.get("StandardOutputContent","")[:800])
        if r.get("StandardErrorContent"):
            print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}...")
    time.sleep(10)
