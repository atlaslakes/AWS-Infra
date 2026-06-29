import os
import boto3, base64, time, json, openpyxl
import urllib3; urllib3.disable_warnings()
from collections import Counter

ssm      = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

def ssm_py(py_code, wait=25, timeout=180):
    b64 = base64.b64encode(py_code.encode()).decode()
    resp = ssm.send_command(
        InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [
            f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/op.py'",
            "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/op.py'",
        ]}, TimeoutSeconds=timeout,
    )
    cmd_id = resp["Command"]["CommandId"]
    time.sleep(wait)
    for _ in range(20):
        r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
        if r["Status"] in ("Success","Failed","Cancelled","TimedOut"):
            return r["Status"], r.get("StandardOutputContent",""), r.get("StandardErrorContent","")
        time.sleep(8)
    return "Timeout","",""

# ── rebuild item list ─────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx", read_only=True, data_only=True)
ws = wb.active
rows_raw = list(ws.iter_rows(values_only=True))
headers  = [str(h).replace("\n"," ").strip() if h else "" for h in rows_raw[0]]

def get_item_group(brand, desc):
    t = (brand + " " + desc).lower()
    if any(w in t for w in ["charcoal","mesquite"]):                           return "Charcoal"
    if "oil" in t and not any(w in t for w in ["pickle","olive"]):             return "Oils & Ghee"
    if any(w in t for w in ["ghee"]):                                          return "Oils & Ghee"
    if any(w in t for w in ["bean","lentil","chickpea","fava","chori","cowpea",
                              "kidney","lima","adzuki","pea","haleem","bajella",
                              "white beans","baked beans","processed peas"]):  return "Beans & Pulses"
    if any(w in t for w in ["rice","basmati","barley","corn meal","corn flour",
                              "corn grits","whole corn","wheat","ugali","corn"]): return "Rice & Grains"
    if any(w in t for w in ["vermicelli","breadstick"]):                       return "Pasta & Noodles"
    if any(w in t for w in ["cheese","nabulsi"]):                              return "Dairy & Cheese"
    if any(w in t for w in ["pickle","pickled","giardinera","hot pepper"]) \
       and "olive" not in t:                                                   return "Pickles & Olives"
    if any(w in t for w in ["olive","olives"]):                                return "Pickles & Olives"
    if any(w in t for w in ["walnut","almond","sesame","raisin","peanut",
                              "sunflower","seed","nut "]):                     return "Nuts & Seeds"
    if any(w in t for w in ["spice","seasoning","stock","marinade","emulsion",
                              "tahini","halawa","lemon","molasses"]):          return "Spices & Herbs"
    if any(w in t for w in ["sauce","salsa","topping","caramel","grape leaves","syrup"]) \
       and "vimto" not in t:                                                   return "Condiments & Sauces"
    if any(w in t for w in ["tea","juice","drink","water","nectar","vimto",
                              "barbican","freez","shani","jannat","ulker tea",
                              "chocolate","hot choc","malt"]):                 return "Beverages"
    if any(w in t for w in ["chip","biscuit","cookie","candy","croissant",
                              "flan","finger biscuit","dolci"]):               return "Snacks & Sweets"
    return "General"

PREFIX_MAP = {
    "Beans & Pulses":"BEAN","Rice & Grains":"GRAIN","Oils & Ghee":"OIL",
    "Beverages":"BEV","Snacks & Sweets":"SNACK","Nuts & Seeds":"NUT",
    "Dairy & Cheese":"DAIRY","Spices & Herbs":"SPICE","Pickles & Olives":"PICKLE",
    "Pasta & Noodles":"PASTA","Condiments & Sauces":"COND",
    "Charcoal":"CHAR","General":"GEN",
}
counters = {}
def next_code(group):
    prefix = PREFIX_MAP.get(group, "ITEM")
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}-{counters[prefix]:04d}"

xl_rows = []
for row in rows_raw[1:]:
    d = dict(zip(headers, row))
    brand = str(d.get("Brand") or "").strip()
    desc  = str(d.get("Description") or "").strip()
    size  = str(d.get("Size") or "").strip()
    if not brand and not desc: continue
    upc_raw = d.get("UPC")
    if isinstance(upc_raw, float): upc = str(int(upc_raw))
    elif upc_raw: upc = str(upc_raw).strip().split(".")[0]
    else: upc = ""
    if upc == "None": upc = ""
    cases_raw, per_case_raw, our_cost_raw = 0, 1, 0
    for k, v in d.items():
        kl = k.lower()
        if "cases" in kl and "hand" in kl: cases_raw = v
        if "items" in kl and ("case" in kl or "unit" in kl): per_case_raw = v
        if "our" in kl and "cost" in kl: our_cost_raw = v
    try: cases    = int(float(cases_raw))    if cases_raw    else 0
    except: cases = 0
    try: per_case = int(float(per_case_raw)) if per_case_raw else 1
    except: per_case = 1
    try: our_cost = round(float(our_cost_raw), 4) if our_cost_raw else 0.0
    except: our_cost = 0.0
    xl_rows.append({"brand":brand,"desc":desc,"size":size,"upc":upc,
                    "cases":cases,"per_case":per_case,"our_cost":our_cost})

name_counts = Counter(f"{r['brand']}|{r['desc']}" for r in xl_rows)
for r in xl_rows:
    key = f"{r['brand']}|{r['desc']}"
    base = f"{r['brand']} {r['desc']}".strip()
    r["item_name"]  = f"{base} {r['size']}".strip() if name_counts[key] > 1 else base
    r["item_group"] = get_item_group(r["brand"], r["desc"])
    r["item_code"]  = next_code(r["item_group"])

all_brands = sorted(set(r["brand"] for r in xl_rows if r["brand"]))
all_items  = [{
    "item_code":     r["item_code"],
    "item_name":     r["item_name"],
    "item_group":    r["item_group"],
    "brand":         r["brand"],
    "standard_rate": r["our_cost"],
    "package_size":  r["size"],
    "items_per_case": str(r["per_case"]),
    "cases_on_hand": r["cases"],
    "upc":           r["upc"],
} for r in xl_rows]

# ── 1. Create brands ──────────────────────────────────────────────────────────
print("=== [1] Creating brands ===")
brands_json = json.dumps(all_brands)
st, out, err = ssm_py(f"""
import frappe, json
frappe.init(site="karavanimports.com"); frappe.connect(); frappe.set_user("Administrator")
existing = set(r[0] for r in frappe.db.sql("SELECT name FROM `tabBrand`", as_list=True))
brands = json.loads('''{brands_json}''')
n = 0
for b in brands:
    if b not in existing:
        try:
            frappe.get_doc({{"doctype":"Brand","brand":b}}).insert(ignore_permissions=True)
            n += 1
        except Exception as e: print(f"ERR {{b}}: {{e}}")
frappe.db.commit()
print(f"Brands created: {{n}}, total: {{len(existing)+n}}")
""", wait=15)
print(f"  {st}: {out.strip()}")

# ── 2. Get existing item codes ─────────────────────────────────────────────────
print("\n=== [2] Getting existing items ===")
import requests; requests.packages.urllib3.disable_warnings()
URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr":"Administrator","pwd":os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
existing_codes = set()
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item", params={"fields":'["name"]',"limit":100,"limit_start":page*100}, timeout=30)
    batch = r.json().get("data",[])
    if not batch: break
    existing_codes.update(b["name"] for b in batch); page += 1
print(f"  Existing: {len(existing_codes)}")

to_create = [it for it in all_items if it["item_code"] not in existing_codes]
print(f"  To create: {len(to_create)}")

# ── 3. Insert in batches of 50 ────────────────────────────────────────────────
print("\n=== [3] Inserting in batches ===")
BATCH = 50
total_created = total_failed = 0

INSERT_TMPL = """
import frappe, json
frappe.init(site="karavanimports.com"); frappe.connect(); frappe.set_user("Administrator")
items = json.loads('''{items_json}''')
created = failed = 0
for it in items:
    for attempt in range(2):
        try:
            doc = frappe.get_doc({{
                "doctype":"Item","item_code":it["item_code"],"item_name":it["item_name"],
                "item_group":it["item_group"],"brand":it["brand"] or None,
                "stock_uom":"Nos","is_stock_item":1,"standard_rate":it["standard_rate"],
                "package_size":it["package_size"] or None,
                "items_per_case":it["items_per_case"] or None,"cases_on_hand":it["cases_on_hand"],
            }})
            if attempt == 0 and it["upc"]:
                doc.append("barcodes", {{"barcode":it["upc"],"barcode_type":""}})
            doc.insert(ignore_permissions=True)
            created += 1; break
        except Exception as e:
            if attempt == 0: continue
            print(f"FAIL {{it['item_code']}}: {{e}}"); failed += 1
frappe.db.commit()
print(f"created={{created}} failed={{failed}}")
"""

for i in range(0, len(to_create), BATCH):
    batch = to_create[i:i+BATCH]
    items_json = json.dumps(batch)
    py = INSERT_TMPL.format(items_json=items_json)
    st, out, err = ssm_py(py, wait=30, timeout=180)
    print(f"  batch {i//BATCH+1}: {st} — {out.strip()}")
    if err and "FAIL" in err: print(f"    ERR: {err[:200]}")

# Final count
print("\n=== Done ===")
page = 0; final = 0
while True:
    r = s.get(f"{URL}/api/resource/Item", params={"fields":'["name"]',"limit":100,"limit_start":page*100}, timeout=30)
    batch = r.json().get("data",[])
    if not batch: break
    final += len(batch); page += 1
print(f"Total items in ERPNext: {final} / {len(all_items)} expected")
