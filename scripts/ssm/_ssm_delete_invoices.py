import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

frappe.db.sql("SET FOREIGN_KEY_CHECKS=0")

tables = [
    # Sales Invoice
    "tabSales Invoice Item",
    "tabSales Invoice Payment",
    "tabSales Invoice Timesheet",
    "tabSales Invoice",
    # Sales Order
    "tabSales Order Item",
    "tabSales Order Packaging Item",
    "tabSales Order",
    # Delivery Note
    "tabDelivery Note Item",
    "tabDelivery Note",
    # Purchase Invoice
    "tabPurchase Invoice Item",
    "tabPurchase Invoice",
    # Purchase Order
    "tabPurchase Order Item",
    "tabPurchase Order",
    # Purchase Receipt
    "tabPurchase Receipt Item",
    "tabPurchase Receipt",
    # Payments
    "tabPayment Entry Reference",
    "tabPayment Entry",
    # Accounting
    "tabGL Entry",
    "tabPayment Ledger Entry",
    "tabJournal Entry Account",
    "tabJournal Entry",
    # Stock (transaction entries only — opening stock SLEs preserved)
    "tabStock Entry Detail",
    "tabStock Entry",
]

total = 0
for t in tables:
    try:
        count = frappe.db.sql(f"SELECT COUNT(*) FROM `{t}`")[0][0]
        frappe.db.sql(f"DELETE FROM `{t}`")
        print(f"  Cleared {count:5} rows: {t}")
        total += count
    except Exception as e:
        print(f"  Skip {t}: {e}")

# Delete only transaction SLEs — preserve opening stock entries
sle_count = frappe.db.sql(
    "SELECT COUNT(*) FROM `tabStock Ledger Entry` WHERE voucher_no != 'OPENING-STOCK'"
)[0][0]
frappe.db.sql("DELETE FROM `tabStock Ledger Entry` WHERE voucher_no != 'OPENING-STOCK'")
print(f"  Cleared {sle_count:5} rows: tabStock Ledger Entry (transactions only)")

# Recalculate bin actual_qty from remaining SLEs (opening stock)
frappe.db.sql("""
    UPDATE `tabBin` b
    SET actual_qty = COALESCE(
        (SELECT SUM(s.actual_qty) FROM `tabStock Ledger Entry` s
         WHERE s.item_code = b.item_code AND s.warehouse = b.warehouse AND s.is_cancelled = 0),
        0),
    projected_qty = COALESCE(
        (SELECT SUM(s.actual_qty) FROM `tabStock Ledger Entry` s
         WHERE s.item_code = b.item_code AND s.warehouse = b.warehouse AND s.is_cancelled = 0),
        0)
""")
print("  Bin quantities restored from opening SLEs")

frappe.db.sql("SET FOREIGN_KEY_CHECKS=1")
frappe.db.commit()
print(f"\\nDONE — {total} total rows removed")
"""

b64 = base64.b64encode(py.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/delinv.py'",
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/delinv.py'",
    ]}, TimeoutSeconds=90)
cid = resp["Command"]["CommandId"]
print(f"CommandId: {cid}")
time.sleep(15)
for _ in range(10):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {r['Status']}")
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent"): print("ERR:", r["StandardErrorContent"][:300])
        break
    print(f"  {r['Status']}..."); time.sleep(8)
