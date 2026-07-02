import os
import boto3, base64, time, json, openpyxl, requests
import urllib3; urllib3.disable_warnings()
from collections import Counter

ssm      = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

def ssm_py(py, wait=20, timeout=120):
    b64 = base64.b64encode(py.encode()).decode()
    resp = ssm.send_command(
        InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
        Parameters={"commands":[
            f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/op.py'",
            "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/op.py'",
        ]}, TimeoutSeconds=timeout)
    cid = resp["Command"]["CommandId"]
    time.sleep(wait)
    for _ in range(15):
        r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
        if r["Status"] in ("Success","Failed","Cancelled","TimedOut"):
            return r["Status"], r.get("StandardOutputContent",""), r.get("StandardErrorContent","")
        time.sleep(8)
    return "Timeout","",""

# rebuild full item list to find the 4 missing ones
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr":"Administrator","pwd":os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
existing = set()
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item", params={"fields":'["name"]',"limit":100,"limit_start":page*100}, timeout=30)
    batch = r.json().get("data",[]);
    if not batch: break
    existing.update(b["name"] for b in batch); page += 1

wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx", read_only=True, data_only=True)
ws = wb.active
rows_raw = list(ws.iter_rows(values_only=True))
headers  = [str(h).replace("\n"," ").strip() if h else "" for h in rows_raw[0]]

def get_item_group(brand, desc):
    t = (brand + " " + desc).lower()
    if any(w in t for w in ["charcoal","mesquite"]): return "Charcoal"
    if "oil" in t and not any(w in t for w in ["pickle","olive"]): return "Oils & Ghee"
    if "ghee" in t: return "Oils & Ghee"
    if any(w in t for w in ["bean","lentil","chickpea","fava","chori","cowpea","kidney","lima",
                              "adzuki","pea","haleem","bajella","white beans","baked beans","processed peas"]):
        return "Beans & Pulses"
    if any(w in t for w in ["rice","basmati","barley","corn meal","corn flour","corn grits",
                              "whole corn","wheat","ugali","corn"]): return "Rice & Grains"
    if any(w in t for w in ["vermicelli","breadstick"]): return "Pasta & Noodles"
    if any(w in t for w in ["cheese","nabulsi"]): return "Dairy & Cheese"
    if any(w in t for w in ["pickle","pickled","giardinera","hot pepper"]) and "olive" not in t:
        return "Pickles & Olives"
    if any(w in t for w in ["olive","olives"]): return "Pickles & Olives"
    if any(w in t for w in ["walnut","almond","sesame","raisin","peanut","sunflower","seed","nut "]):
        return "Nuts & Seeds"
    if any(w in t for w in ["spice","seasoning","stock","marinade","emulsion","tahini","halawa","lemon","molasses"]):
        return "Spices & Herbs"
    if any(w in t for w in ["sauce","salsa","topping","caramel","grape leaves","syrup"]) and "vimto" not in t:
        return "Condiments & Sauces"
    if any(w in t for w in ["tea","juice","drink","water","nectar","vimto","barbican","freez",
                              "shani","jannat","ulker tea","chocolate","malt"]): return "Beverages"
    if any(w in t for w in ["chip","biscuit","cookie","candy","croissant","flan","finger biscuit","dolci"]):
        return "Snacks & Sweets"
    return "General"

PREFIX_MAP = {"Beans & Pulses":"BEAN","Rice & Grains":"GRAIN","Oils & Ghee":"OIL","Beverages":"BEV",
              "Snacks & Sweets":"SNACK","Nuts & Seeds":"NUT","Dairy & Cheese":"DAIRY","Spices & Herbs":"SPICE",
              "Pickles & Olives":"PICKLE","Pasta & Noodles":"PASTA","Condiments & Sauces":"COND",
              "Charcoal":"CHAR","General":"GEN"}
counters = {}
def next_code(group):
    p = PREFIX_MAP.get(group,"ITEM"); counters[p] = counters.get(p,0)+1; return f"{p}-{counters[p]:04d}"

xl_rows = []
for row in rows_raw[1:]:
    d = dict(zip(headers, row))
    brand = str(d.get("Brand") or "").strip(); desc = str(d.get("Description") or "").strip()
    size  = str(d.get("Size") or "").strip()
    if not brand and not desc: continue
    upc_raw = d.get("UPC")
    if isinstance(upc_raw, float): upc = str(int(upc_raw))
    elif upc_raw: upc = str(upc_raw).strip().split(".")[0]
    else: upc = ""
    if upc == "None": upc = ""
    cases_raw = per_case_raw = our_cost_raw = 0
    for k, v in d.items():
        kl = k.lower()
        if "cases" in kl and "hand" in kl: cases_raw = v
        if "items" in kl and ("case" in kl or "unit" in kl): per_case_raw = v
        if "our" in kl and "cost" in kl: our_cost_raw = v
    try: cases = int(float(cases_raw)) if cases_raw else 0
    except: cases = 0
    try: per_case = int(float(per_case_raw)) if per_case_raw else 1
    except: per_case = 1
    try: our_cost = round(float(our_cost_raw), 4) if our_cost_raw else 0.0
    except: our_cost = 0.0
    xl_rows.append({"brand":brand,"desc":desc,"size":size,"upc":upc,"cases":cases,"per_case":per_case,"our_cost":our_cost})

name_counts = Counter(f"{r['brand']}|{r['desc']}" for r in xl_rows)
for r in xl_rows:
    key = f"{r['brand']}|{r['desc']}"
    base = f"{r['brand']} {r['desc']}".strip()
    r["item_name"]  = f"{base} {r['size']}".strip() if name_counts[key] > 1 else base
    r["item_group"] = get_item_group(r["brand"], r["desc"])
    r["item_code"]  = next_code(r["item_group"])

missing = [r for r in xl_rows if r["item_code"] not in existing]
print(f"Missing items: {len(missing)}")
for r in missing:
    print(f"  {r['item_code']:14} {r['item_name'][:50]}")

if not missing:
    print("All items exist!"); exit(0)

# Use direct SQL insert for these problematic items
import re, datetime
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

rows_sql = []
for r in missing:
    def esc(v): return str(v or "").replace("\\","\\\\").replace("'","\\'")
    rows_sql.append(
        f"('{esc(r['item_code'])}','{esc(r['item_name'])}','{esc(r['item_group'])}','{esc(r['brand'])}','Nos',1,"
        f"{r['our_cost']},'{esc(r['size'])}','{esc(str(r['per_case']))}',{r['cases']},'{NOW}','{NOW}',"
        f"'Administrator','Administrator')"
    )

sql_values = ",\n".join(rows_sql)

py = f"""
import frappe
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

frappe.db.sql(\"\"\"
INSERT INTO `tabItem`
  (name, item_name, item_group, brand, stock_uom, is_stock_item,
   standard_rate, package_size, items_per_case, cases_on_hand,
   creation, modified, owner, modified_by)
VALUES {sql_values}
\"\"\")

# add barcodes for items that have UPC
"""

# add barcode inserts
for r in missing:
    if r["upc"]:
        upc_esc = r["upc"].replace("'","\\'")
        code_esc = r["item_code"].replace("'","\\'")
        py += f"""
try:
    frappe.db.sql("INSERT INTO `tabItem Barcode` (name,parent,parenttype,parentfield,barcode) VALUES ('{code_esc}-bc','{code_esc}','Item','barcodes','{upc_esc}')")
except: pass
"""

py += """
frappe.db.commit()
total = frappe.db.sql("SELECT COUNT(*) FROM `tabItem`")[0][0]
print(f"Done. Total items: {total}")
"""

print("\nInserting via direct SQL...")
st, out, err = ssm_py(py, wait=20)
print(f"Status: {st}")
print(out.strip())
if err: print("ERR:", err[:200])
