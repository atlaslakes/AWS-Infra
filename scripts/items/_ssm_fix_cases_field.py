import boto3, base64, time, json, openpyxl
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Build UPC -> cases map from Excel
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx", read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).replace("\n", " ").strip() if h else "" for h in rows[0]]
xl_by_upc = {}
for row in rows[1:]:
    d = dict(zip(headers, row))
    upc_raw = d.get("UPC")
    if isinstance(upc_raw, float): upc = str(int(upc_raw))
    elif upc_raw: upc = str(upc_raw).strip().split(".")[0]
    else: upc = ""
    if not upc or upc == "None": continue
    cases_raw = 0
    for k, v in d.items():
        if "cases" in k.lower() and "hand" in k.lower():
            cases_raw = v
    try: cases = int(float(cases_raw)) if cases_raw else 0
    except: cases = 0
    xl_by_upc[upc] = cases

# Load barcodes
with open("_barcodes.json") as f:
    bc_data = json.load(f)
item_barcodes = {}
for b in bc_data:
    item_barcodes.setdefault(b["item_code"], []).append(str(b["barcode"]).strip())

# Build full item_code -> cases mapping
updates = {}
for item_code, barcodes in item_barcodes.items():
    for bc in barcodes:
        if bc in xl_by_upc:
            updates[item_code] = xl_by_upc[bc]
            break

updates_json = json.dumps(updates)
print(f"Total items to update via SQL: {len(updates)}")

py = f"""
import frappe, json
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

updates = json.loads('''{updates_json}''')
count = 0
for item_code, cases in updates.items():
    frappe.db.sql("UPDATE `tabItem` SET cases_on_hand=%s WHERE name=%s", (cases, item_code))
    count += 1

frappe.db.commit()
print(f"Updated {{count}} items via SQL")

# Verify a few
sample = frappe.db.sql(
    "SELECT name, cases_on_hand FROM `tabItem` WHERE cases_on_hand > 0 ORDER BY name LIMIT 10",
    as_dict=True
)
for r in sample:
    print(f"  {{r['name']:14}} cases_on_hand={{r['cases_on_hand']}}")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/fix_cases.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fix_cases.py'",
]

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
                        Parameters={"commands": commands}, Comment="fix cases field", TimeoutSeconds=120)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(20)
for _ in range(10):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", "")[:2000])
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
