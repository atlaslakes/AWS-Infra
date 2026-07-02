import os
import boto3, base64, time
import requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# 1. Create custom field "stock" on Item
print("Creating custom field 'stock'...")
cf_check = s.get(f"{URL}/api/resource/Custom Field",
                 params={"filters": '[["dt","=","Item"],["fieldname","=","stock"]]',
                         "fields": '["name"]'}, timeout=15)
if cf_check.json().get("data"):
    print("  Already exists")
else:
    r = s.post(f"{URL}/api/resource/Custom Field", json={
        "dt":           "Item",
        "fieldname":    "stock",
        "label":        "Stock",
        "fieldtype":    "Int",
        "insert_after": "cases_on_hand",
    }, timeout=30)
    print(f"  {'Created' if r.status_code in (200,201) else 'FAILED'}: {r.status_code}")
    if r.status_code not in (200,201): print(r.text[:200])

# 2. Copy cases_on_hand -> stock via SSM SQL
ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.db.sql("UPDATE `tabItem` SET stock = cases_on_hand")
frappe.db.commit()
n = frappe.db.sql("SELECT COUNT(*) FROM `tabItem` WHERE stock > 0")[0][0]
print(f"Done. Items with stock > 0: {n}")
sample = frappe.db.sql("SELECT name, cases_on_hand, stock FROM `tabItem` WHERE stock > 0 LIMIT 5", as_dict=True)
for r in sample:
    print(f"  {r['name']:14} cases_on_hand={r['cases_on_hand']}  stock={r['stock']}")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands":[
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/st.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/st.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
print("Copying cases_on_hand -> stock via SQL...")
time.sleep(15)
for _ in range(8):
    r2 = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r2["Status"] in ("Success","Failed","Cancelled","TimedOut"):
        print(f"Status: {r2['Status']}")
        print(r2.get("StandardOutputContent",""))
        if r2.get("StandardErrorContent"): print("ERR:", r2["StandardErrorContent"][:200])
        break
    time.sleep(8)
