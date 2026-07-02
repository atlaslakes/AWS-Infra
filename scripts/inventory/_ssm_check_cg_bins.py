import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()

# Check Bin for California Garden items
print("=== Bins for California Garden (BEAN-0008 to BEAN-0024, etc.) ===")
cg_items = ["BEAN-0008","BEAN-0009","BEAN-0010","BEAN-0011","BEAN-0012",
            "BEAN-0013","BEAN-0014","BEAN-0015","BEAN-0016","BEAN-0017",
            "BEAN-0018","BEAN-0019","BEAN-0020","BEAN-0021","BEAN-0022",
            "BEAN-0023","BEAN-0024","GEN-0004","RICE-0013","SPICE-0003"]

bins = frappe.db.sql(
    "SELECT b.item_code, b.actual_qty FROM `tabBin` b WHERE b.item_code IN %s",
    (cg_items,), as_dict=True
)
bin_map = {b['item_code']: b['actual_qty'] for b in bins}
for ic in cg_items:
    print(f"  {ic:14} actual_qty={bin_map.get(ic, 'NO BIN')}")

# Check last SLE for BEAN-0009
print("\\n=== Last 5 SLEs for BEAN-0009 ===")
sles = frappe.db.sql(
    "SELECT posting_date, qty_after_transaction, actual_qty, voucher_type, voucher_no "
    "FROM `tabStock Ledger Entry` WHERE item_code='BEAN-0009' "
    "ORDER BY posting_date DESC, creation DESC LIMIT 5",
    as_dict=True
)
for s in sles:
    print(f"  {s['posting_date']} | qty_after={s['qty_after_transaction']} | actual_qty={s['actual_qty']} | {s['voucher_type']} {s['voucher_no']}")

# Check reconciliation MAT-RECO-2026-00009 items for BEAN-0009
print("\\n=== MAT-RECO-2026-00009 items for BEAN-0009 ===")
rows = frappe.db.sql(
    "SELECT item_code, qty, valuation_rate, current_qty, current_valuation_rate "
    "FROM `tabStock Reconciliation Item` "
    "WHERE parent='MAT-RECO-2026-00009' AND item_code='BEAN-0009'",
    as_dict=True
)
for r in rows:
    print(f"  {r}")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/chk.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/chk.py'",
]

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
                        Parameters={"commands": commands}, Comment="check bins", TimeoutSeconds=60)
cmd_id = resp["Command"]["CommandId"]
time.sleep(15)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", "")[:3000])
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}..."); time.sleep(10)
