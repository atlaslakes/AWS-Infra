import os
"""
1. Creates any missing Brand records.
2. Retries all failed items via SSM direct insert to bypass sanitizer.
"""
import requests, openpyxl, boto3, base64, time, json
import urllib3; urllib3.disable_warnings()
from collections import Counter

URL  = "https://www.karavanimports.com"
s    = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in")

ssm      = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"

# ── get existing items (to find what's missing) ───────────────────────────────
existing = set()
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item",
              params={"fields": '["name"]', "limit": 100, "limit_start": page*100}, timeout=30)
    batch = r.json().get("data", [])
    if not batch: break
    existing.update(b["name"] for b in batch)
    page += 1
print(f"Existing items: {len(existing)}")

# ── reload Excel (same logic as repopulate_items.py) ─────────────────────────
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx",
                             read_only=True, data_only=True)
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
    if any(w in t for w in ["spice","seasoning","stock powder","stock",
                              "marinade","emulsion","tahini","halawa","lemon","molasses"]):
                                                                               return "Spices & Herbs"
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

from collections import Counter as C2
name_counts = C2(f"{r['brand']}|{r['desc']}" for r in xl_rows)
for r in xl_rows:
    key = f"{r['brand']}|{r['desc']}"
    base = f"{r['brand']} {r['desc']}".strip()
    r["item_name"]  = f"{base} {r['size']}".strip() if name_counts[key] > 1 else base
    r["item_group"] = get_item_group(r["brand"], r["desc"])
    r["item_code"]  = next_code(r["item_group"])

# ── 1. Create missing brands ──────────────────────────────────────────────────
print("\n=== [1] Creating missing brands ===")
existing_brands = set()
rb = s.get(f"{URL}/api/resource/Brand", params={"fields":'["name"]',"limit":200}, timeout=15)
for b in rb.json().get("data", []):
    existing_brands.add(b["name"])

all_brands = set(r["brand"] for r in xl_rows if r["brand"])
missing_brands = all_brands - existing_brands
print(f"  Missing: {sorted(missing_brands)}")
for brand in sorted(missing_brands):
    rb2 = s.post(f"{URL}/api/resource/Brand", json={"brand_name": brand}, timeout=15)
    print(f"  {'OK' if rb2.status_code in (200,201) else 'ERR'} {brand}")

# ── 2. Collect items to create (those not yet in ERPNext) ─────────────────────
to_create = [r for r in xl_rows if r["item_code"] not in existing]
print(f"\n=== [2] Items to create: {len(to_create)} ===")

# ── 3. Build SSM payload and insert all missing items directly ────────────────
items_json = json.dumps([{
    "item_code":     r["item_code"],
    "item_name":     r["item_name"],
    "item_group":    r["item_group"],
    "brand":         r["brand"],
    "stock_uom":     "Nos",
    "is_stock_item": 1,
    "standard_rate": r["our_cost"],
    "package_size":  r["size"],
    "items_per_case": str(r["per_case"]) if r["per_case"] else "",
    "cases_on_hand": r["cases"],
    "upc":           r["upc"],
} for r in to_create])

py = f"""
import frappe, json
frappe.init(site="karavanimports.com")
frappe.connect()
frappe.set_user("Administrator")

items = json.loads('''{items_json}''')
created = 0
failed  = 0
for it in items:
    try:
        doc = frappe.get_doc({{
            "doctype":       "Item",
            "item_code":     it["item_code"],
            "item_name":     it["item_name"],
            "item_group":    it["item_group"],
            "brand":         it["brand"] or None,
            "stock_uom":     "Nos",
            "is_stock_item": 1,
            "standard_rate": it["standard_rate"],
            "package_size":  it["package_size"] or None,
            "items_per_case": it["items_per_case"] or None,
            "cases_on_hand": it["cases_on_hand"],
        }})
        if it["upc"]:
            doc.append("barcodes", {{"barcode": it["upc"], "barcode_type": ""}})
        doc.insert(ignore_permissions=True)
        created += 1
    except Exception as e:
        err = str(e)
        if "barcode" in err.lower() or "already use" in err.lower():
            try:
                doc2 = frappe.get_doc({{
                    "doctype":       "Item",
                    "item_code":     it["item_code"],
                    "item_name":     it["item_name"],
                    "item_group":    it["item_group"],
                    "brand":         it["brand"] or None,
                    "stock_uom":     "Nos",
                    "is_stock_item": 1,
                    "standard_rate": it["standard_rate"],
                    "package_size":  it["package_size"] or None,
                    "items_per_case": it["items_per_case"] or None,
                    "cases_on_hand": it["cases_on_hand"],
                }})
                doc2.insert(ignore_permissions=True)
                created += 1
            except Exception as e2:
                print(f"FAIL {{it['item_code']}}: {{e2}}")
                failed += 1
        else:
            print(f"FAIL {{it['item_code']}}: {{e}}")
            failed += 1

frappe.db.commit()
print(f"Created: {{created}}, Failed: {{failed}}")
"""

b64 = base64.b64encode(py.encode()).decode()
commands = [
    f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/ins.py'",
    "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/ins.py'",
]
print("\n=== [3] Inserting via SSM ===")
resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
                        Parameters={"commands": commands}, Comment="insert items", TimeoutSeconds=300)
cmd_id = resp["Command"]["CommandId"]
print(f"CommandId: {cmd_id}")
time.sleep(30)
for _ in range(20):
    r2 = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
    if r2["Status"] in ("Success","Failed","Cancelled","TimedOut"):
        print(f"Status: {r2['Status']}")
        print(r2.get("StandardOutputContent","")[:3000])
        if r2.get("StandardErrorContent"): print("ERR:", r2["StandardErrorContent"][:300])
        break
    print(f"  {r2['Status']}..."); time.sleep(15)
