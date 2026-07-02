import os
"""
Updates Standard Selling Item Price from Data_06_23.csv.
Match order: 1) UPC exact  2) Brand + Description + Size fuzzy
Price/Item and Price/Case in Inventory Manager come from tabItem Price Standard Selling.
"""
import requests, csv, re, json, time, boto3, base64
from difflib import SequenceMatcher
requests.packages.urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s   = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

ssm      = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"


# ── helpers ───────────────────────────────────────────────────────────────────
def norm(v):
    if not v: return ""
    v = str(v).lower().strip()
    v = re.sub(r"[^\w\s]", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def sim(a, b): return SequenceMatcher(None, norm(a), norm(b)).ratio()

def clean_upc(v):
    if not v: return ""
    return re.sub(r"[^\d]", "", str(v).strip().lstrip("`"))

def upc_variants(u):
    """Return a set of normalized variants to try matching against."""
    u = clean_upc(u)
    if not u: return set()
    variants = {u, u.lstrip("0")}
    if len(u) >= 2: variants.add(u[:-2])           # drop last 2 digits
    if len(u) >= 3: variants.add(u[:-2].lstrip("0"))
    if len(u) >= 12: variants.add(u[-12:])
    if len(u) >= 11: variants.add(u[-11:])
    return {v for v in variants if v}

def upc_match(erp_upcs, csv_upc, csv_toast=""):
    csv_vars = upc_variants(csv_upc) | upc_variants(csv_toast)
    if not csv_vars: return False
    for eu in erp_upcs:
        erp_vars = upc_variants(eu)
        if erp_vars & csv_vars:  # any overlap
            return True
    return False

def to_grams(val, unit):
    unit = unit.lower().strip()
    conv = {"g":1,"gr":1,"gram":1,"grams":1,"kg":1000,"oz":28.3495,"oz.":28.3495,
            "lb":453.592,"lbs":453.592,"ml":1,"l":1000,"fl oz":29.5735}
    return val * conv.get(unit, 0) if unit in conv else None

SIZE_RE = re.compile(r"([\d.]+)\s*([a-z\s]+)", re.I)
def sizes_match(a, b, tol=0.06):
    if norm(a) == norm(b): return True
    def parse(v):
        m = SIZE_RE.match(str(v).strip())
        if not m: return None
        try: num = float(m.group(1))
        except: return None
        return to_grams(num, m.group(2).strip())
    ga, gb = parse(a), parse(b)
    if ga and gb: return abs(ga-gb)/max(ga,gb) <= tol
    return False


# ── 1. Load CSV ───────────────────────────────────────────────────────────────
print("=== [1] Loading CSV ===")
csv_items = []
with open("Data_06_23.csv", encoding="utf-8", errors="replace") as f:
    for row in csv.DictReader(f):
        brand    = (row.get("Branddescription") or "").strip()
        size     = (row.get("Sizedescription")  or "").strip()
        expanded = (row.get("Expandeddescription") or "").strip()
        pos_desc = (row.get("POSdescription") or "").strip()
        upc      = clean_upc(row.get("UPCcode") or "")
        toast    = clean_upc(row.get("TOAST_UPCCODE") or "")
        price_raw = (row.get("Activeprice") or row.get("Price") or "").strip()
        try: price = float(price_raw) if price_raw else None
        except: price = None
        if not brand and not expanded: continue
        if not price or price <= 0: continue
        desc = expanded
        if size and desc.lower().endswith(size.lower()):
            desc = desc[:-len(size)].strip()
        csv_items.append({"brand":brand,"desc":desc,"size":size,
                          "expanded":expanded,"pos_desc":pos_desc,
                          "upc":upc,"toast":toast,"price":price})
print(f"  {len(csv_items)} priced rows")

# build UPC variant -> csv_item index (all normalized forms)
csv_by_upc = {}
for c in csv_items:
    for u in [c["upc"], c["toast"]]:
        for var in upc_variants(u):
            csv_by_upc.setdefault(var, c)


# ── 2. Load ERPNext items + barcodes ─────────────────────────────────────────
print("\n=== [2] Loading ERPNext items ===")
erp_items = []
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item",
              params={"fields":'["name","item_name","brand","package_size","standard_rate","items_per_case"]',
                      "limit":100,"limit_start":page*100}, timeout=30)
    batch = r.json().get("data",[])
    if not batch: break
    erp_items.extend(batch); page += 1
print(f"  {len(erp_items)} items")

# Get all barcodes
r_bc = s.get(f"{URL}/api/resource/Item Barcode",
             params={"fields":'["parent","barcode"]',"limit":1000}, timeout=30)
item_barcodes = {}
for b in r_bc.json().get("data",[]):
    item_barcodes.setdefault(b["parent"],[]).append(clean_upc(b["barcode"]))

# If REST returns 0 barcodes, load from cached file
if not item_barcodes:
    try:
        with open("_barcodes.json") as f:
            for b in json.load(f):
                item_barcodes.setdefault(b["item_code"],[]).append(clean_upc(b["barcode"]))
        print(f"  Loaded barcodes from cache: {len(item_barcodes)} items")
    except: pass

# Enrich items
for item in erp_items:
    brand = (item.get("brand") or "").strip()
    iname = (item.get("item_name") or "").strip()
    desc  = iname[len(brand):].strip() if brand and iname.lower().startswith(brand.lower()) else iname
    item["_desc"]  = desc
    item["_brand"] = brand
    item["_size"]  = (item.get("package_size") or "").strip()
    item["_upcs"]  = item_barcodes.get(item["name"], [])


# ── 3. Match ──────────────────────────────────────────────────────────────────
print("\n=== [3] Matching ===")
matched = []
unmatched = []

for item in erp_items:
    # Try UPC first (all variants)
    csv_m = None
    for upc in item["_upcs"]:
        for var in upc_variants(upc):
            if var in csv_by_upc:
                csv_m = csv_by_upc[var]
                break
        if csv_m: break

    # Fallback: brand + desc + size fuzzy
    if not csv_m:
        best_score, best = 0, None
        eb = norm(item["_brand"])
        for c in csv_items:
            cb = norm(c["brand"])
            # brand match: exact, one contains other, or known aliases
            if eb != cb and eb not in cb and cb not in eb:
                continue
            if not sizes_match(item["_size"], c["size"]): continue
            score = max(sim(item["_desc"], c["desc"]),
                        sim(item["_desc"], c["expanded"]),
                        sim(item["_desc"], c["pos_desc"]))
            if score >= 0.45 and score > best_score:
                best_score, best = score, c
        csv_m = best

    if csv_m:
        matched.append((item, csv_m))
    else:
        unmatched.append(item)

print(f"  Matched  : {len(matched)}")
print(f"  Unmatched: {len(unmatched)}")


# ── 4. Update prices ──────────────────────────────────────────────────────────
print("\n=== [4] Updating prices ===")

# Load existing Standard Selling prices
existing_prices = {}
page = 0
while True:
    r = s.get(f"{URL}/api/resource/Item Price",
              params={"fields":'["name","item_code","price_list_rate"]',
                      "filters":'[["price_list","=","Standard Selling"]]',
                      "limit":500,"limit_start":page*500}, timeout=30)
    batch = r.json().get("data",[])
    if not batch: break
    for p in batch: existing_prices[p["item_code"]] = p
    page += 1
print(f"  Existing Standard Selling prices: {len(existing_prices)}")

sql_updates = {}  # item_code -> price, for SSM SQL fallback
ok = skip = fail = 0

for item, csv_m in matched:
    item_code = item["name"]
    price     = csv_m["price"]
    old_rate  = float(item.get("standard_rate") or 0)

    # Update standard_rate if changed
    if abs(old_rate - price) > 0.01:
        r2 = s.post(f"{URL}/api/method/frappe.client.set_value",
                    json={"doctype":"Item","name":item_code,
                          "fieldname":"standard_rate","value":price}, timeout=15)
        if r2.status_code not in (200,201):
            sql_updates[item_code] = price

    # Upsert Standard Selling Item Price
    if item_code in existing_prices:
        ep = existing_prices[item_code]
        if abs(float(ep.get("price_list_rate") or 0) - price) < 0.01:
            skip += 1; continue
        rp = s.put(f"{URL}/api/resource/Item%20Price/{ep['name']}",
                   json={"price_list_rate": price}, timeout=15)
    else:
        rp = s.post(f"{URL}/api/resource/Item Price", json={
            "item_code": item_code, "price_list": "Standard Selling",
            "price_list_rate": price, "selling": 1, "currency": "USD",
        }, timeout=15)

    if rp.status_code in (200,201): ok += 1
    else:
        fail += 1
        sql_updates[item_code] = price

    time.sleep(0.03)

print(f"  OK: {ok}  Skipped: {skip}  Failed: {fail}")


# ── 5. SSM SQL fallback ───────────────────────────────────────────────────────
if sql_updates:
    print(f"\n=== [5] SQL fallback for {len(sql_updates)} items ===")
    updates_json = json.dumps(sql_updates)
    py = f"""
import frappe, json
frappe.init(site="karavanimports.com"); frappe.connect(); frappe.set_user("Administrator")
updates = json.loads('''{updates_json}''')
for ic, price in updates.items():
    frappe.db.sql("UPDATE `tabItem` SET standard_rate=%s WHERE name=%s", (price, ic))
    existing = frappe.db.get_value("Item Price", {{"item_code":ic,"price_list":"Standard Selling"}}, "name")
    if existing:
        frappe.db.sql("UPDATE `tabItem Price` SET price_list_rate=%s WHERE name=%s", (price, existing))
    else:
        frappe.get_doc({{"doctype":"Item Price","item_code":ic,"price_list":"Standard Selling",
                         "price_list_rate":price,"selling":1,"currency":"USD"}}).insert(ignore_permissions=True)
frappe.db.commit()
print(f"SQL fallback: {{len(updates)}} items updated")
"""
    b64 = base64.b64encode(py.encode()).decode()
    resp = ssm.send_command(InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
        Parameters={"commands":[
            f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/pr.py'",
            "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/pr.py'",
        ]}, TimeoutSeconds=120)
    cid = resp["Command"]["CommandId"]
    time.sleep(20)
    for _ in range(10):
        r3 = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCE)
        if r3["Status"] in ("Success","Failed","Cancelled","TimedOut"):
            print(f"  {r3['Status']}: {r3.get('StandardOutputContent','').strip()}")
            break
        time.sleep(8)

print(f"""
=== Summary ===
Matched  : {len(matched)} / {len(erp_items)}
Unmatched: {len(unmatched)} (no price set)
Prices updated: {ok} via API + {len(sql_updates)} via SQL fallback
Skipped (unchanged): {skip}
""")
if unmatched[:5]:
    print("Sample unmatched:")
    for u in unmatched[:10]:
        print(f"  {u['name']:14} {u['item_name'][:45]}")
