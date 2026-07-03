import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# Step 1: Run query + write CSV on the container
script_text = "\n".join([
    "import frappe, csv",
    "frappe.init(site='karavanimports.com')",
    "frappe.connect()",
    "frappe.set_user('Administrator')",
    "sql = (",
    "    'SELECT i.item_code, i.item_name, i.brand,'",
    "    ' i.custom_sku AS sku, i.custom_invoice_alias AS invoice_alias,'",
    "    ' ib.barcode AS upc_barcode, i.package_size AS size,'",
    "    ' i.items_per_case,'",
    "    ' COALESCE(SUM(b.actual_qty),0) AS cases_on_hand,'",
    "    ' ip.price_list_rate AS standard_price,'",
    "    ' ip2.price_list_rate AS buying_price'",
    "    ' FROM `tabItem` i'",
    "    ' LEFT JOIN `tabBin` b ON b.item_code = i.item_code'",
    "    ' LEFT JOIN (SELECT parent, barcode FROM `tabItem Barcode` GROUP BY parent) ib ON ib.parent = i.item_code'",
    "    ' LEFT JOIN `tabItem Price` ip'",
    "    '   ON ip.item_code = i.item_code AND ip.price_list = %s AND ip.selling = 1'",
    "    ' LEFT JOIN `tabItem Price` ip2'",
    "    '   ON ip2.item_code = i.item_code AND ip2.price_list = %s AND ip2.buying = 1'",
    "    ' WHERE i.disabled = 0'",
    "    ' GROUP BY i.item_code'",
    "    ' ORDER BY i.brand, i.item_name'",
    ")",
    "rows = frappe.db.sql(sql, ('Standard Selling', 'Standard Buying'), as_dict=True)",
    "no_price = [r for r in rows if not r['standard_price']]",
    "rough = [r for r in rows if r['standard_price'] and float(r['standard_price']) <= 1.0]",
    "combined = []",
    "for r in no_price:",
    "    r['price_status'] = 'NO PRICE'",
    "    combined.append(r)",
    "for r in rough:",
    "    r['price_status'] = 'ROUGH ESTIMATE'",
    "    combined.append(r)",
    "combined.sort(key=lambda x: (x.get('brand') or '', x.get('item_name') or ''))",
    "fields = ['item_code','item_name','brand','sku','invoice_alias','upc_barcode','size','items_per_case','cases_on_hand','standard_price','buying_price','price_status']",
    "with open('/tmp/items_missing_price.csv', 'w', newline='') as f:",
    "    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')",
    "    w.writeheader()",
    "    for r in combined:",
    "        w.writerow({k: (r.get(k) or '') for k in fields})",
    "print('DONE total=%d no_price=%d rough=%d' % (len(rows), len(no_price), len(rough)))",
])

b64 = base64.b64encode(script_text.encode()).decode()

resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/noprice2.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/noprice2.py'",
        "docker cp frappe_docker-backend-1:/tmp/items_missing_price.csv /tmp/items_missing_price.csv",
        "cat /tmp/items_missing_price.csv",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
time.sleep(16)

output = ""
for _ in range(10):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        output = r.get("StandardOutputContent", "")
        err = r.get("StandardErrorContent", "").strip()
        if err:
            print("STDERR:", err[:600])
        break
    time.sleep(6)

if not output.strip():
    print("No output.")
    exit(1)

# The output contains the DONE line + CSV content
lines = output.splitlines()
done_line = next((l for l in lines if l.startswith("DONE")), None)
if done_line:
    print(done_line)

# Find CSV start (header line)
csv_start = next((i for i, l in enumerate(lines) if l.startswith("item_code,")), None)
if csv_start is None:
    print("Could not find CSV in output:")
    print(output[:500])
    exit(1)

csv_content = "\n".join(lines[csv_start:])
outfile = r"C:\Users\aizen\Desktop\AWS\data\items_missing_price.csv"
with open(outfile, "w", newline="", encoding="utf-8") as f:
    f.write(csv_content)

row_count = len([l for l in lines[csv_start+1:] if l.strip()])
print(f"CSV saved: {outfile}")
print(f"Rows written: {row_count}")
