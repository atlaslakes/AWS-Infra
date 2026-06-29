"""
Sets the Sales Invoice naming series counter to 4999 in ERPNext,
so the next invoice created will be numbered 5000.
"""
import base64, json, subprocess, time, sys

PYTHON = '''
import frappe
frappe.init(site="frontend")
frappe.connect()

rows = frappe.get_all("Sales Invoice", fields=["naming_series"], limit=1)
series = rows[0]["naming_series"] if rows else "SINV-"
print("Naming series:", series)

cur = frappe.db.sql("SELECT current FROM tabSeries WHERE name=%s", series)
print("Current counter:", cur[0][0] if cur else "not found")

if cur:
    frappe.db.sql("UPDATE tabSeries SET current=4999 WHERE name=%s", series)
else:
    frappe.db.sql("INSERT INTO tabSeries (name, current) VALUES (%s, 4999)", series)

frappe.db.commit()

new_cur = frappe.db.sql("SELECT current FROM tabSeries WHERE name=%s", series)
print("New counter:", new_cur[0][0] if new_cur else "?")
print("SUCCESS — next Sales Invoice will be #5000")
'''

b64 = base64.b64encode(PYTHON.encode()).decode()

ssm = {
    "InstanceIds": ["i-0baea513db2b15557"],
    "DocumentName": "AWS-RunShellScript",
    "Parameters": {
        "commands": [
            f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/set_series.py'",
            "docker exec frappe_docker-backend-1 bash -lc 'mkdir -p /home/frappe/frappe-bench/logs && cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/set_series.py'"
        ]
    }
}

json_path = r"C:\Users\aizen\Desktop\AWS\_ssm_series.json"
with open(json_path, "w") as f:
    json.dump(ssm, f, indent=2)
print("SSM JSON written.")

result = subprocess.run(
    ["aws", "ssm", "send-command", "--no-verify-ssl", "--cli-input-json", f"file://{json_path}"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print("send-command failed:", result.stderr)
    sys.exit(1)

cmd_id = json.loads(result.stdout)["Command"]["CommandId"]
print(f"Command sent: {cmd_id}")
print("Waiting 15s for completion...")
time.sleep(15)

inv = subprocess.run(
    ["aws", "ssm", "get-command-invocation", "--no-verify-ssl",
     "--command-id", cmd_id,
     "--instance-id", "i-0baea513db2b15557"],
    capture_output=True, text=True
)
data = json.loads(inv.stdout)
print("Status:", data.get("Status"))
print("--- stdout ---")
print(data.get("StandardOutputContent", ""))
if data.get("StandardErrorContent"):
    print("--- stderr ---")
    print(data["StandardErrorContent"][:400])
