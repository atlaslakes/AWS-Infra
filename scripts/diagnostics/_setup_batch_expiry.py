import boto3, base64, time, json, math
import pandas as pd
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Load Excel
df = pd.read_excel("aws-infra/Karavan Inventory-updated.xlsx")
df.columns = [c.strip().replace("\n", " ") for c in df.columns]

upc_data = {}
for _, row in df.iterrows():
    upc_raw   = row.get("UPC") or ""
    cases_raw = row.get("Cases  On Hand") or row.get("Cases On Hand") or 0
    cost_raw  = row.get("Our Cost") or 1
    exp_raw   = row.get("Expiry Date") or row.get("Expiry") or row.get("Exp Date") or ""
    try:
        upc   = str(int(float(str(upc_raw).strip()))) if upc_raw else ""
        cases = int(float(str(cases_raw))) if cases_raw else 0
        cost  = float(str(cost_raw)) if cost_raw else 1.0
        if math.isnan(cost) or cost <= 0: cost = 1.0
    except: continue
    if upc and cases > 0:
        upc_data[upc] = {"cases": cases, "cost": cost, "expiry": str(exp_raw) if exp_raw else ""}

with open("_barcodes.json") as f:
    barcodes = json.load(f)

item_stock = {}
for b in barcodes:
    try: upc = str(int(float(b["barcode"])))
    except: upc = b["barcode"]
    if upc in upc_data:
        item_stock[b["item_code"]] = upc_data[upc]

print("Matched %d items" % len(item_stock))

# Write remote script to a local file then encode
remote_script = """import frappe, json
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

WAREHOUSE = "Stores - AL"
COMPANY   = "Atlas Lakes"

with open("/tmp/stock_data.json") as f:
    item_stock = json.load(f)

print("Enabling batch tracking on all items...")
frappe.db.sql("UPDATE `tabItem` SET has_batch_no=1, create_new_batch=1 WHERE disabled=0")
frappe.db.commit()

print("Clearing existing stock...")
frappe.db.sql("DELETE FROM `tabStock Ledger Entry`")
frappe.db.sql("DELETE FROM `tabBin`")
frappe.db.sql("DELETE FROM `tabStock Reconciliation Item`")
frappe.db.sql("DELETE FROM `tabStock Reconciliation`")
frappe.db.sql("DELETE FROM `tabBatch`")
frappe.db.commit()

expense_acc = "Temporary Opening - AL"
cost_center = frappe.db.get_value("Company", COMPANY, "cost_center") or ""

ok = err = 0
for item_code, data in item_stock.items():
    try:
        qty    = data["cases"]
        cost   = data["cost"]
        expiry = data.get("expiry", "") or ""
        if expiry in ("nan", "NaT", "None", ""): expiry = None

        batch_id = "BTCH-" + item_code
        batch = frappe.get_doc({
            "doctype": "Batch",
            "item": item_code,
            "batch_id": batch_id,
            "expiry_date": expiry,
            "manufacturing_date": "2026-01-01",
        })
        batch.flags.ignore_permissions = True
        batch.insert(ignore_permissions=True)
        frappe.db.commit()

        # Verify batch exists in DB
        saved_batch = frappe.db.get_value("Batch", {"batch_id": batch_id, "item": item_code}, "name")
        if not saved_batch:
            raise Exception("Batch not found after insert: " + batch_id)

        sr = frappe.new_doc("Stock Reconciliation")
        sr.purpose = "Opening Stock"
        sr.posting_date = "2026-01-01"
        sr.posting_time = "00:00:00"
        sr.company = COMPANY
        sr.expense_account = expense_acc
        sr.cost_center = cost_center
        sr.append("items", {
            "item_code": item_code,
            "warehouse": WAREHOUSE,
            "qty": qty,
            "valuation_rate": cost,
            "batch_no": saved_batch,
        })
        sr.flags.ignore_permissions = True
        sr.flags.ignore_mandatory = True
        sr.insert(ignore_permissions=True)
        sr.submit()
        ok += 1
    except Exception as e:
        err += 1
        if err <= 5:
            print("  ERR %s: %s" % (item_code, str(e)[:100]))

frappe.db.commit()
print("Done: %d OK, %d errors" % (ok, err))
bins = frappe.db.sql("SELECT COUNT(*) FROM `tabBin` WHERE actual_qty > 0")[0][0]
print("Bins with stock: %d" % bins)
print("DONE")
"""

data_b64   = base64.b64encode(json.dumps(item_stock).encode()).decode()
script_b64 = base64.b64encode(remote_script.encode()).decode()

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/stock_data.json'" % data_b64,
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/batchsetup.py'" % script_b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/batchsetup.py'",
    ]}, TimeoutSeconds=600)
cid = resp["Command"]["CommandId"]
print("CommandId: %s" % cid)
time.sleep(40)
for _ in range(30):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status: %s" % r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:500])
        break
    print("  %s..." % r["Status"]); time.sleep(20)
