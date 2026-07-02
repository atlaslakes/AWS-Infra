import boto3, json, time, urllib3, base64
urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

py_script = """
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()

updates = [
    ("BEV-0007",    3.99),
    ("BEV-0008",    1.29),
    ("BEV-0015",    1.79),
    ("BEV-0016",    2.99),
    ("DAIRY-0008",  6.99),
    ("DAIRY-0009", 12.99),
    ("DAIRY-0010", 24.99),
    ("PICKLE-0019", 4.99),
    ("PICKLE-0020", 14.99),
]

for item_code, price in updates:
    frappe.db.sql(
        "UPDATE `tabItem` SET standard_rate=%s, custom_price=%s WHERE name=%s",
        (price, price, item_code)
    )
    print("Updated", item_code, price)

frappe.db.commit()
print("COMMITTED OK")
"""

b64 = base64.b64encode(py_script.encode()).decode()

commands = [
    # Step 1: decode script inside the container
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/fix_prices.py'",
    # Step 2: run it
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/fix_prices.py'",
]

resp = ssm.send_command(
    InstanceIds=[INSTANCE],
    DocumentName="AWS-RunShellScript",
    Parameters={"commands": commands},
    Comment="price SQL fix 9 items",
    TimeoutSeconds=120,
)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")

time.sleep(20)
for attempt in range(10):
    result = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    status = result["Status"]
    if status in ("Success", "Failed", "Cancelled", "TimedOut"):
        print(f"Status: {status}")
        print("STDOUT:", result.get("StandardOutputContent", "")[:1000])
        err = result.get("StandardErrorContent", "")
        if err:
            print("STDERR:", err[:400])
        break
    print(f"  {status}... waiting")
    time.sleep(10)
