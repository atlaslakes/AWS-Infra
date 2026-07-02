import boto3, base64, time, json
import pandas as pd
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Load Excel
df = pd.read_excel("aws-infra/Karavan Inventory-updated.xlsx")
df.columns = [c.strip().replace("\n", " ") for c in df.columns]
upc_data = {}  # upc -> {cases, cost}
for _, row in df.iterrows():
    upc_raw = row.get("UPC") or ""
    cases_raw = row.get("Cases  On Hand") or row.get("Cases On Hand") or 0
    cost_raw  = row.get("Our Cost") or 1
    try:
        upc   = str(int(float(str(upc_raw).strip()))) if upc_raw else ""
        cases = int(float(str(cases_raw))) if cases_raw else 0
        import math
        cost  = float(str(cost_raw)) if cost_raw else 1.0
        if math.isnan(cost) or cost <= 0: cost = 1.0
    except: cost = 1.0
    if upc and cases > 0: upc_data[upc] = {"cases": cases, "cost": cost}

with open("_barcodes.json") as f:
    barcodes = json.load(f)

item_stock = {}  # item_code -> {qty, valuation_rate}
for b in barcodes:
    try: upc = str(int(float(b["barcode"])))
    except: upc = b["barcode"]
    if upc in upc_data:
        item_stock[b["item_code"]] = upc_data[upc]

print("Matched %d items" % len(item_stock))
stock_json = json.dumps(item_stock)

# Write the remote script to a temp file, then base64 encode
remote_script = r"""
import frappe, json
from frappe.utils import today
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

WAREHOUSE = "Stores - AL"
COMPANY   = "Atlas Lakes"

with open("/tmp/stock_data.json") as f:
    item_stock = json.load(f)

# Clear everything
frappe.db.sql("UPDATE `tabItem` SET is_stock_item=1 WHERE disabled=0")
frappe.db.sql("DELETE FROM `tabStock Ledger Entry`")
frappe.db.sql("DELETE FROM `tabBin`")
frappe.db.sql("DELETE FROM `tabStock Reconciliation Item`")
frappe.db.sql("DELETE FROM `tabStock Reconciliation`")
frappe.db.commit()
print("Set all items as stock items, cleared SLEs/Bins/reconciliations")

expense_acc = "Temporary Opening - AL"
cost_center = frappe.db.get_value("Company", COMPANY, "cost_center") or ""

items = list(item_stock.items())
batches = [items[i:i+50] for i in range(0, len(items), 50)]
total_ok = 0

for idx, batch in enumerate(batches):
    try:
        sr = frappe.new_doc("Stock Reconciliation")
        sr.name = "OPENING-STOCK-%03d" % (idx + 1)
        sr.purpose = "Opening Stock"
        sr.posting_date = "2026-01-01"
        sr.posting_time = "00:00:00"
        sr.company = COMPANY
        sr.expense_account = expense_acc
        sr.cost_center = cost_center
        for item_code, data in batch:
            sr.append("items", {
                "item_code": item_code,
                "warehouse": WAREHOUSE,
                "qty": data["cases"],
                "valuation_rate": data["cost"],
            })
        sr.flags.ignore_permissions = True
        sr.flags.ignore_mandatory = True
        sr.insert(ignore_permissions=True)
        sr.submit()
        total_ok += len(batch)
        print("  Batch %d: %d items OK — %s" % (idx+1, len(batch), sr.name))
    except Exception as e:
        print("  Batch %d FAILED (%s), retrying one by one..." % (idx+1, str(e)[:80]))
        for item_code, data in batch:
            try:
                sr2 = frappe.new_doc("Stock Reconciliation")
                sr2.purpose = "Opening Stock"
                sr2.posting_date = "2026-01-01"
                sr2.posting_time = "00:00:00"
                sr2.company = COMPANY
                sr2.expense_account = expense_acc
                sr2.cost_center = cost_center
                sr2.append("items", {
                    "item_code": item_code, "warehouse": WAREHOUSE,
                    "qty": data["cases"], "valuation_rate": data["cost"],
                })
                sr2.flags.ignore_permissions = True
                sr2.flags.ignore_mandatory = True
                sr2.insert(ignore_permissions=True)
                sr2.submit()
                total_ok += 1
            except Exception as e2:
                print("    SKIP %s: %s" % (item_code, str(e2)[:60]))

frappe.db.commit()
print("Total items reconciled: %d" % total_ok)

bin_count = frappe.db.sql("SELECT COUNT(*) FROM `tabBin` WHERE actual_qty > 0")[0][0]
print("tabBin rows with actual_qty > 0: %d" % bin_count)
print("DONE")
"""

# Write stock data to a temp file
with open("/tmp/stock_data_local.json", "w") as f:
    json.dump(item_stock, f)

script_b64 = base64.b64encode(remote_script.encode()).decode()
data_b64   = base64.b64encode(json.dumps(item_stock).encode()).decode()

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"echo {data_b64} | base64 -d > /tmp/stock_data.json",
        f"docker exec frappe_docker-backend-1 bash -c 'echo {data_b64} | base64 -d > /tmp/stock_data.json'",
        f"docker exec frappe_docker-backend-1 bash -c 'echo {script_b64} | base64 -d > /tmp/stockreco.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/stockreco.py'",
    ]}, TimeoutSeconds=300)
cid = resp["Command"]["CommandId"]
print("CommandId: %s" % cid)
time.sleep(30)
for _ in range(20):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status: %s" % r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:800])
        break
    print("  %s..." % r["Status"]); time.sleep(15)
