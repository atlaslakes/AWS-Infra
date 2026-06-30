import boto3, base64, time, json
import pandas as pd
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Load Excel
df = pd.read_excel("aws-infra/Karavan Inventory-updated.xlsx")
df.columns = [c.strip().replace("\n", " ") for c in df.columns]

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

with open("_barcodes.json") as f:
    barcodes = json.load(f)

item_stock = {}
for b in barcodes:
    try:
        upc = str(int(float(b["barcode"])))
    except:
        upc = b["barcode"]
    if upc in upc_cases:
        item_stock[b["item_code"]] = upc_cases[upc]

print(f"Matched {len(item_stock)} items from Excel")
stock_json = json.dumps(item_stock)

py = f"""
import frappe, json
from frappe.utils import today, now_datetime
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

WAREHOUSE = "Stores - AL"
COMPANY   = "Atlas Lakes"
item_stock = json.loads('{stock_json}')

# 1. Wipe all existing SLEs and reset bins to 0 so we start clean
frappe.db.sql("DELETE FROM `tabStock Ledger Entry` WHERE warehouse=%s", (WAREHOUSE,))
frappe.db.sql("UPDATE `tabBin` SET actual_qty=0, projected_qty=0 WHERE warehouse=%s", (WAREHOUSE,))
print("Cleared existing SLEs and Bin quantities")

# 2. Insert one opening SLE per item
posting_date = "2026-01-01"
posting_time = "00:00:00"
inserted = 0
for item_code, qty in item_stock.items():
    name = frappe.generate_hash(length=16)
    sql = ("INSERT INTO `tabStock Ledger Entry` "
           "(name,item_code,warehouse,actual_qty,qty_after_transaction,"
           "voucher_type,voucher_no,stock_uom,posting_date,posting_time,"
           "company,is_cancelled,docstatus,creation,modified,owner,modified_by) "
           "VALUES (%s,%s,%s,%s,%s,'Stock Reconciliation','OPENING-STOCK','Nos',"
           "%s,%s,%s,0,1,NOW(),NOW(),'Administrator','Administrator')")
    frappe.db.sql(sql, (name, item_code, WAREHOUSE, qty, qty, posting_date, posting_time, COMPANY))

    # Sync bin to match
    existing_bin = frappe.db.get_value("Bin", {{"item_code": item_code, "warehouse": WAREHOUSE}}, "name")
    if existing_bin:
        frappe.db.sql("UPDATE `tabBin` SET actual_qty=%s, projected_qty=%s WHERE name=%s",
                      (qty, qty, existing_bin))
    else:
        bname = frappe.generate_hash(length=10)
        frappe.db.sql(
            "INSERT INTO `tabBin` (name,item_code,warehouse,actual_qty,projected_qty,"
            "stock_uom,creation,modified,owner,modified_by) "
            "VALUES (%s,%s,%s,%s,%s,'Nos',NOW(),NOW(),'Administrator','Administrator')",
            (bname, item_code, WAREHOUSE, qty, qty))
    inserted += 1

# 3. Also update cases_on_hand custom field to stay in sync
for item_code, qty in item_stock.items():
    frappe.db.sql("UPDATE `tabItem` SET cases_on_hand=%s WHERE name=%s", (qty, item_code))

# 4. Disable negative stock
frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0)

frappe.db.commit()
print(f"Inserted {{inserted}} opening SLEs")
print("allow_negative_stock = 0")
print("DONE")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/opensle.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/opensle.py'",
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
