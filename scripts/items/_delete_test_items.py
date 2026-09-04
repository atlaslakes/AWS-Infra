import boto3, base64, time
import urllib3; urllib3.disable_warnings()

ssm = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

item_codes = [
    "CHOCA-0054",
    "APETI-0526", "APETI-0525", "APETI-0524", "APETI-0523", "APETI-0522", "APETI-0521", "APETI-0520",
    "APETI-0519", "APETI-0518", "APETI-0517", "APETI-0516", "APETI-0515", "APETI-0514", "APETI-0513",
    "APETI-0512", "APETI-0511", "APETI-0510", "APETI-0509", "APETI-0508", "APETI-0507", "APETI-0506",
    "APETI-0505", "APETI-0504", "APETI-0503", "APETI-0502", "APETI-0501", "APETI-0500", "APETI-0499",
    "APETI-0498", "APETI-0497", "APETI-0496", "APETI-0495", "APETI-0494", "APETI-0493", "APETI-0491",
    "APETI-0490", "APETI-0489", "APETI-0488", "APETI-0487", "APETI-0486", "APETI-0482", "APETI-0481",
    "APETI-0480", "APETI-0479", "APETI-0478", "APETI-0477", "APETI-0476", "APETI-0475", "APETI-0474",
    "APETI-0473", "APETI-0472", "APETI-0471", "APETI-0470", "APETI-0469", "APETI-0468", "APETI-0467",
    "APETI-0466", "APETI-0465", "APETI-0464", "APETI-0463", "APETI-0462", "APETI-0461", "APETI-0460",
    "APETI-0459", "APETI-0458", "APETI-0457", "APETI-0456", "APETI-0455", "APETI-0454", "APETI-0453",
    "APETI-0452", "APETI-0451", "APETI-0450", "APETI-0449", "APETI-0448", "APETI-0446", "APETI-0445",
    "APETI-0444", "APETI-0443", "APETI-0442", "APETI-0441", "APETI-0440", "APETI-0439", "APETI-0438",
    "APETI-0437", "APETI-0436", "APETI-0435", "APETI-0434", "APETI-0433", "APETI-0431", "APETI-0430",
    "APETI-0429", "APETI-0428", "APETI-0427", "APETI-0426", "APETI-0425", "APETI-0424", "APETI-0423",
    "APETI-0422", "APETI-0421", "APETI-0420", "APETI-0419", "APETI-0418", "APETI-0417", "APETI-0416",
    "APETI-0415", "APETI-0414", "APETI-0413", "APETI-0412", "APETI-0411", "APETI-0410", "APETI-0409",
    "APETI-0407", "APETI-0405", "APETI-0404", "APETI-0403", "APETI-0402", "APETI-0399", "APETI-0398",
    "APETI-0397", "APETI-0396", "APETI-0395", "APETI-0392", "APETI-0391", "APETI-0390", "APETI-0388",
    "APETI-0387", "APETI-0386", "APETI-0385", "APETI-0384", "APETI-0383", "APETI-0382", "APETI-0381",
    "APETI-0380", "APETI-0379", "APETI-0378", "APETI-0377", "APETI-0376", "APETI-0375", "APETI-0374",
    "APETI-0373", "APETI-0372", "APETI-0371", "APETI-0370", "APETI-0369", "APETI-0367", "APETI-0366",
    "APETI-0365", "APETI-0364", "APETI-0361", "APETI-0360", "APETI-0359", "APETI-0358", "APETI-0356",
    "APETI-0355", "APETI-0354", "APETI-0353", "APETI-0352", "APETI-0351", "APETI-0350", "APETI-0349",
    "APETI-0348", "APETI-0347", "APETI-0346", "APETI-0345", "APETI-0344", "APETI-0343", "APETI-0342",
    "APETI-0341", "APETI-0340", "APETI-0339", "APETI-0338", "APETI-0337", "APETI-0336", "APETI-0334",
    "APETI-0333", "APETI-0332", "APETI-0331", "APETI-0330", "APETI-0329", "APETI-0328", "APETI-0327",
    "APETI-0325",
]

lines = [
    "import frappe",
    "frappe.init(site='erpnext.karavanimports.com')",
    "frappe.connect()",
    "frappe.set_user('Administrator')",
    "codes = " + repr(item_codes),
    "deleted, disabled, failed = [], [], []",
    "for code in codes:",
    "    try:",
    "        frappe.delete_doc('Item', code, force=True, ignore_permissions=True)",
    "        frappe.db.commit()",
    "        deleted.append(code)",
    "    except Exception as e:",
    "        try:",
    "            frappe.db.set_value('Item', code, 'disabled', 1)",
    "            frappe.db.commit()",
    "            disabled.append(code)",
    "        except Exception as e2:",
    "            failed.append((code, str(e2)[:120]))",
    "print('DELETED (%d): %s' % (len(deleted), ', '.join(deleted)))",
    "print('DISABLED (%d, had linked records): %s' % (len(disabled), ', '.join(disabled)))",
    "print('FAILED (%d):' % len(failed))",
    "for code, err in failed:",
    "    print('  %s | %s' % (code, err))",
]

b64 = base64.b64encode("\n".join(lines).encode()).decode()
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
    Parameters={"commands": [
        "docker exec frappe_docker-backend-1 bash -c 'echo %s | base64 -d > /tmp/deletetestitems.py'" % b64,
        "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/deletetestitems.py'",
    ]}, TimeoutSeconds=60)
cid = resp["Command"]["CommandId"]
time.sleep(16)
for _ in range(20):
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        print("Status:", r["Status"])
        print(r.get("StandardOutputContent", ""))
        if r.get("StandardErrorContent", "").strip():
            print("ERR:", r["StandardErrorContent"][:600])
        break
    time.sleep(6)
