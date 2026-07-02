import boto3, base64, time, json, openpyxl
import urllib3; urllib3.disable_warnings()

ssm      = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Build UPC -> cases map from Excel
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx", read_only=True, data_only=True)
ws = wb.active
rows_raw = list(ws.iter_rows(values_only=True))
headers  = [str(h).replace("\n"," ").strip() if h else "" for h in rows_raw[0]]

xl_by_upc = {}
for row in rows_raw[1:]:
    d = dict(zip(headers, row))
    upc_raw = d.get("UPC")
    if isinstance(upc_raw, float): upc = str(int(upc_raw))
    elif upc_raw: upc = str(upc_raw).strip().split(".")[0]
    else: upc = ""
    if not upc or upc == "None": continue
    cases_raw = 0
    for k, v in d.items():
        if "cases" in k.lower() and "hand" in k.lower(): cases_raw = v
    try: cases = int(float(cases_raw)) if cases_raw else 0
    except: cases = 0
    xl_by_upc[upc] = cases

xl_json = json.dumps(xl_by_upc)
print(f"Excel UPC entries: {len(xl_by_upc)}")

py = f"""
import frappe, json
frappe.init(site="karavanimports.com")
frappe.connect()

xl = json.loads('''{xl_json}''')

# Get all barcodes -> item_code mapping
rows = frappe.db.sql("SELECT barcode, parent FROM `tabItem Barcode`", as_dict=True)
matched = updated = 0
for r in rows:
    upc = str(r["barcode"]).strip()
    if upc in xl:
        cases = xl[upc]
        frappe.db.sql("UPDATE `tabItem` SET cases_on_hand=%s WHERE name=%s", (cases, r["parent"]))
        matched += 1
        if cases > 0:
            updated += 1

frappe.db.commit()
print(f"Matched: {{matched}} barcodes, {{updated}} with non-zero cases")

# Also reset all to 0 first for items without a barcode match
total = frappe.db.sql("SELECT COUNT(*) FROM `tabItem`")[0][0]
nonzero = frappe.db.sql("SELECT COUNT(*) FROM `tabItem` WHERE cases_on_hand > 0")[0][0]
print(f"Total items: {{total}}, with stock: {{nonzero}}")

# Sample
sample = frappe.db.sql(
    "SELECT i.name, i.item_name, i.cases_on_hand FROM `tabItem` i WHERE i.cases_on_hand > 0 LIMIT 10",
    as_dict=True
)
for r in sample:
    print(f"  {{r['name']:14}} {{r['cases_on_hand']:4}} cases  {{r['item_name'][:40]}}")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/sc.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/sc.py'",
]

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
                        Parameters={"commands": commands}, Comment="set cases", TimeoutSeconds=120)
cid = resp["Command"]["CommandId"]
print(f"CommandId: {cid}")
time.sleep(20)
for _ in range(12):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent","")[:3000])
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:200])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
