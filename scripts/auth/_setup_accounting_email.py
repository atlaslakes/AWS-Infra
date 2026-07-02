import os, requests, boto3, base64, time
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

remote_script = """import frappe, traceback
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

src = frappe.get_doc("Email Account", "Karavan Imports")
print("Source fields: smtp=%s port=%s tls=%s login=%s auth=%s service=%s" % (
    src.smtp_server, src.smtp_port, src.use_tls, src.login_id, src.auth_method, src.service))

if frappe.db.exists("Email Account", "accounting@karavanimports.com"):
    print("Account already exists — skipping create")
else:
    try:
        new_acc = frappe.get_doc({
            "doctype":            "Email Account",
            "email_id":           "accounting@karavanimports.com",
            "email_account_name": "Accounting - Karavan",
            "service":            src.service or "GMail",
            "smtp_server":        src.smtp_server,
            "smtp_port":          src.smtp_port,
            "use_tls":            src.use_tls,
            "login_id":           src.login_id or src.email_id,
            "password":           src.password,
            "auth_method":        src.auth_method or "Basic",
            "enable_outgoing":    1,
            "default_outgoing":   0,
            "enable_incoming":    0,
        })
        new_acc.flags.ignore_permissions = True
        new_acc.flags.ignore_validate = True
        new_acc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Created: accounting@karavanimports.com")
    except Exception:
        print("CREATE FAILED:")
        traceback.print_exc()

# Send test regardless (uses default outgoing if accounting not set up yet)
try:
    frappe.sendmail(
        recipients=["youssef@atlaslakes.com"],
        subject="Test - accounting@karavanimports.com",
        message="<p>Test email from <b>accounting@karavanimports.com</b> via ERPNext.</p>",
        sender="accounting@karavanimports.com",
    )
    frappe.db.commit()
    print("Test email queued to youssef@atlaslakes.com")
except Exception:
    print("SEND FAILED:")
    traceback.print_exc()
"""

b64 = base64.b64encode(remote_script.encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/accemail.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/accemail.py'",
    ]}, TimeoutSeconds=40)
cid = resp["Command"]["CommandId"]
time.sleep(12)
for _ in range(8):
    r2 = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r2["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r2["Status"])
        print(r2.get("StandardOutputContent", ""))
        if r2.get("StandardErrorContent"): print("ERR:", r2["StandardErrorContent"][:1500])
        break
    print(" ", r2["Status"]); time.sleep(8)
