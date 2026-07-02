"""
Applies Stock Reconciliations to bring ERPNext cases_on_hand in line with the CSV.
Runs batches of 20 items via SSM inside the container to avoid timeouts.
"""
import os, requests, csv, boto3, base64, time, json, math
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

# ── Pull live ERPNext inventory ────────────────────────────────────────────────
r = s.get(f"{URL}/api/method/frappe.desk.query_report.run",
          params={"report_name": "Inventory Manager", "ignore_prepared_report": 1}, timeout=60)
erp_rows = [x for x in r.json().get("message", {}).get("result", []) if isinstance(x, dict)]

UPC_KEY = next((k for k in (erp_rows[0].keys() if erp_rows else []) if "upc" in k.lower() or "barcode" in k.lower()), None)
erp_by_upc  = {}
erp_by_name = {}
erp_by_id   = {row["item_id"]: row for row in erp_rows if row.get("item_id")}
for row in erp_rows:
    upc = str(row.get(UPC_KEY) or "").strip()
    if upc:
        erp_by_upc.setdefault(upc, []).append(row)
    erp_by_name[row.get("description","").strip().lower()] = row

# ── Read CSV ───────────────────────────────────────────────────────────────────
csv_rows = []
with open("Karavan Inventory - Sheet1.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        try:
            qty = float(str(row.get("Cases On Hand","0") or "0").strip())
        except ValueError:
            qty = 0
        csv_rows.append({"brand": row.get("Brand","").strip(),
                         "description": row.get("Description","").strip(),
                         "upc": str(row.get("UPC","") or "").strip(),
                         "csv_qty": qty})

# ── Build list of items that need updating ────────────────────────────────────
updates = []
for c in csv_rows:
    erp = None
    if c["upc"] and c["upc"] in erp_by_upc:
        candidates = erp_by_upc[c["upc"]]
        if len(candidates) == 1:
            erp = candidates[0]
        else:
            d = c["description"].lower()
            erp = min(candidates, key=lambda x: len(set(x.get("description","").lower().split()) ^ set(d.split())))
    if not erp:
        erp = erp_by_name.get(c["description"].lower())
    if not erp:
        continue
    erp_qty = erp.get("cases_on_hand") or 0
    target  = c["csv_qty"]
    if target != erp_qty:
        updates.append({"item_code": erp["item_id"], "qty": target,
                        "description": c["description"]})

print(f"Items to reconcile: {len(updates)}")
for u in updates:
    print(f"  {u['item_code']:14} {u['description'][:40]:40} -> {u['qty']}")

# ── Send batches to SSM ────────────────────────────────────────────────────────
BATCH = 20
ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

def run_batch(items):
    items_json = json.dumps(items)
    remote = f"""import frappe, json, traceback
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

WAREHOUSE = "Stores - AL"
COMPANY   = "Atlas Lakes"
items = json.loads({repr(items_json)})
ok, fail = 0, 0

for item in items:
    item_code = item["item_code"]
    target_qty = item["qty"]
    try:
        cost = frappe.db.get_value("Item Price",
            {{"item_code": item_code, "price_list": "Standard Selling"}}, "price_list_rate") or 1.0
        if not cost or cost <= 0: cost = 1.0
        sr = frappe.get_doc({{
            "doctype":   "Stock Reconciliation",
            "purpose":   "Opening Stock",
            "company":   COMPANY,
            "expense_account": "Temporary Opening - AL",
            "items": [{{
                "item_code":      item_code,
                "warehouse":      WAREHOUSE,
                "qty":            target_qty,
                "valuation_rate": cost,
            }}],
        }})
        sr.flags.ignore_permissions = True
        sr.insert(ignore_permissions=True)
        sr.submit()
        ok += 1
        print("OK:", item_code, "->", target_qty)
    except Exception as e:
        fail += 1
        print("FAIL:", item_code, str(e)[:120])

frappe.db.commit()
print(f"Batch done: {{ok}} ok, {{fail}} failed")
"""
    b64 = base64.b64encode(remote.encode()).decode()
    resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [
            "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/reco_batch.py'" % b64,
            "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/reco_batch.py'",
        ]}, TimeoutSeconds=120)
    cid = resp["Command"]["CommandId"]
    time.sleep(20)
    for _ in range(12):
        r2 = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
        if r2["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
            print(r2.get("StandardOutputContent",""))
            if r2.get("StandardErrorContent","").strip():
                print("ERR:", r2["StandardErrorContent"][:400])
            return
        time.sleep(10)

batches = [updates[i:i+BATCH] for i in range(0, len(updates), BATCH)]
for i, batch in enumerate(batches):
    print(f"\n=== Batch {i+1}/{len(batches)} ===")
    run_batch(batch)

print("\nAll batches done. Verify in Inventory Manager.")
