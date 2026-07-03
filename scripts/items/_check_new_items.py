import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

script_text = "\n".join([
    "import frappe",
    "frappe.init(site='karavanimports.com')",
    "frappe.connect()",
    "frappe.set_user('Administrator')",
    # New items created today
    "new_items = frappe.db.sql(",
    "    'SELECT name, item_name, brand, item_group, creation FROM `tabItem`"
    "     WHERE DATE(creation) = CURDATE() AND disabled = 0"
    "     ORDER BY creation',",
    "    as_dict=True)",
    "print('NEW ITEMS TODAY: %d' % len(new_items))",
    "for i in new_items:",
    "    print('  [%s] %s | brand=%s | group=%s' % (i['name'], i['item_name'], i['brand'], i['item_group']))",
    # Existing item code patterns
    "print()",
    "print('EXISTING CODE PATTERNS (sample):')",
    "patterns = frappe.db.sql(",
    "    'SELECT name FROM `tabItem` WHERE disabled=0 AND name REGEXP %s ORDER BY name LIMIT 30',",
    "    ('^[A-Z]+-[0-9]+$',), as_dict=True)",
    "for p in patterns:",
    "    print('  ' + p['name'])",
    # Show all distinct prefixes used
    "print()",
    "print('ALL PREFIXES IN USE:')",
    "prefixes = frappe.db.sql(",
    "    \"SELECT SUBSTRING_INDEX(name, '-', 1) AS prefix, COUNT(*) AS cnt"
    "     FROM `tabItem` WHERE disabled=0 AND name REGEXP '^[A-Z]+-[0-9]+$'"
    "     GROUP BY prefix ORDER BY prefix\",",
    "    as_dict=True)",
    "for p in prefixes:",
    "    # Find max number used",
    "    mx = frappe.db.sql(",
    "        'SELECT MAX(CAST(SUBSTRING_INDEX(name, \"-\", -1) AS UNSIGNED)) AS mx"
    "         FROM `tabItem` WHERE name LIKE %s',",
    "        (p['prefix'] + '-%',), as_dict=True)",
    "    print('  %s: %d items, next would be %s-%04d' % (p['prefix'], p['cnt'], p['prefix'], (mx[0]['mx'] or 0)+1))",
])

b64 = base64.b64encode(script_text.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/newitemcheck.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/newitemcheck.py'",
    ]}, TimeoutSeconds=30)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(8):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:600])
        break
    time.sleep(5)
