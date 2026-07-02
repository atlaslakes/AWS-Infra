import boto3, base64, time, json
import pandas as pd
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Load Excel
df = pd.read_excel("aws-infra/Karavan Inventory-updated.xlsx")
df.columns = [c.strip().replace("\n", " ") for c in df.columns]

# Build UPC -> cases map from Excel
upc_cases = {}
for _, row in df.iterrows():
    upc_raw = row.get("UPC") or ""
    cases_raw = row.get("Cases  On Hand") or row.get("Cases On Hand") or 0
    try:
        upc = str(int(float(str(upc_raw).strip()))) if upc_raw else ""
        cases = int(float(str(cases_raw))) if cases_raw else 0
    except:
        continue
    if upc and cases > 0:
        upc_cases[upc] = cases

print(f"Excel: {len(upc_cases)} items with stock from UPC")

# Load barcode -> item_code from cache
with open("_barcodes.json") as f:
    barcodes = json.load(f)

# Build item_code -> cases
item_stock = {}
for b in barcodes:
    item_code = b["item_code"]
    barcode = b["barcode"]
    try:
        upc = str(int(float(barcode)))
    except:
        upc = barcode
    if upc in upc_cases:
        item_stock[item_code] = upc_cases[upc]

print(f"Matched: {len(item_stock)} items to ERPNext item codes")

# Send to ERPNext via SSM
stock_json = json.dumps(item_stock)

py = f"""
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

import json
WAREHOUSE = "Stores - AL"
item_stock = json.loads('{stock_json}')

print(f"Loading {{len(item_stock)}} items into tabBin and cases_on_hand...")

# Clear existing bin quantities first
frappe.db.sql("UPDATE `tabBin` SET actual_qty=0, projected_qty=0 WHERE warehouse=%s", (WAREHOUSE,))

inserted = updated = 0
for item_code, qty in item_stock.items():
    # Update cases_on_hand custom field
    frappe.db.sql("UPDATE `tabItem` SET cases_on_hand=%s WHERE name=%s", (qty, item_code))

    # Upsert tabBin
    existing = frappe.db.get_value("Bin", {{"item_code": item_code, "warehouse": WAREHOUSE}}, "name")
    if existing:
        frappe.db.sql(
            "UPDATE `tabBin` SET actual_qty=%s, projected_qty=%s WHERE name=%s",
            (qty, qty, existing))
        updated += 1
    else:
        bin_name = frappe.generate_hash(length=10)
        frappe.db.sql(
            "INSERT INTO `tabBin` (name,item_code,warehouse,actual_qty,projected_qty,stock_uom,creation,modified,owner,modified_by) "
            "VALUES (%s,%s,%s,%s,%s,'Nos',NOW(),NOW(),'Administrator','Administrator')",
            (bin_name, item_code, WAREHOUSE, qty, qty))
        inserted += 1

frappe.db.commit()
print(f"  Inserted: {{inserted}}  Updated: {{updated}}")
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/resetstock.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/resetstock.py'",
    ]}, TimeoutSeconds=120)
cid = resp["Command"]["CommandId"]
print(f"CommandId: {cid}")
time.sleep(20)
for _ in range(12):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:500])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
