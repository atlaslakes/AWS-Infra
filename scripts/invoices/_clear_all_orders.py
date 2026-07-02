import os, requests, boto3, base64, time
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

def get_all(doctype, status_code):
    r = s.get(f"{URL}/api/resource/{doctype}",
              params={"filters": f'[["docstatus","=",{status_code}]]',
                      "fields": '["name"]', "limit": 500}, timeout=15)
    return [row["name"] for row in r.json().get("data", [])]

for doctype in ["Sales Invoice", "Sales Order"]:
    draft     = get_all(doctype, 0)
    submitted = get_all(doctype, 1)
    cancelled = get_all(doctype, 2)
    print(f"{doctype}: {len(draft)} draft, {len(submitted)} submitted, {len(cancelled)} cancelled")

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote = """import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

for doctype in ["Sales Invoice", "Sales Order"]:
    all_names = frappe.get_all(doctype, fields=["name","docstatus"], limit_page_length=500)
    print(f"\\n{doctype}: {len(all_names)} total")

    # Cancel submitted first
    for doc in all_names:
        if doc["docstatus"] == 1:
            try:
                d = frappe.get_doc(doctype, doc["name"])
                d.flags.ignore_permissions = True
                d.cancel()
                frappe.db.commit()
                print(f"  Cancelled: {doc['name']}")
            except Exception as e:
                print(f"  Cancel FAIL {doc['name']}: {str(e)[:100]}")

    # Delete all (draft + cancelled)
    all_names2 = frappe.get_all(doctype, fields=["name"], limit_page_length=500)
    for doc in all_names2:
        try:
            frappe.delete_doc(doctype, doc["name"], force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  Deleted: {doc['name']}")
        except Exception as e:
            print(f"  Delete FAIL {doc['name']}: {str(e)[:100]}")

print("\\nDone.")
"""

b64 = base64.b64encode(remote.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/clearall.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/clearall.py'",
    ]}, TimeoutSeconds=120)
cid = resp["Command"]["CommandId"]
print("Running...")
time.sleep(20)
for _ in range(12):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent",""))
        if r.get("StandardErrorContent","").strip(): print("ERR:", r["StandardErrorContent"][:600])
        break
    print(" ", r["Status"]); time.sleep(10)
