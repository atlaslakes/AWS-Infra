import os
"""
1. Deletes all current items and linked records (bins, barcodes, SLEs).
2. Recreates items from Karavan Inventory-updated.xlsx.
   - Item code: category prefix + sequential (BEAN-0001, OIL-0001, etc.)
   - Item name: Brand + Description (+ Size if duplicate name)
   - Brand, package_size, items_per_case, cases_on_hand from Excel
   - Barcode from UPC column
   - Item group inferred from brand/description keywords
"""
import requests, openpyxl, boto3, base64, time
import urllib3; urllib3.disable_warnings()

URL  = "https://www.karavanimports.com"
s    = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

ssm      = boto3.client("ssm", region_name="us-east-1", verify=False)
INSTANCE = "i-0baea513db2b15557"


# ── helpers ───────────────────────────────────────────────────────────────────
def ssm_run(py_code, timeout=120):
    b64 = base64.b64encode(py_code.encode()).decode()
    resp = ssm.send_command(
        InstanceIds=[INSTANCE], DocumentName="AWS-RunShellScript",
        Parameters={"commands": [
            f"docker exec frappe_docker-backend-1 bash -c 'echo {b64} | base64 -d > /tmp/op.py'",
            "docker exec frappe_docker-backend-1 bash -lc 'cd /home/frappe/frappe-bench/sites && ../env/bin/python /tmp/op.py'",
        ]}, TimeoutSeconds=timeout,
    )
    cmd_id = resp["Command"]["CommandId"]
    time.sleep(20)
    for _ in range(20):
        r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE)
        if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
            return r["Status"], r.get("StandardOutputContent",""), r.get("StandardErrorContent","")
        time.sleep(10)
    return "Timeout", "", ""

def get_item_group(brand, desc):
    t = (brand + " " + desc).lower()
    if any(w in t for w in ["charcoal", "mesquite"]):                          return "Charcoal"
    if any(w in t for w in ["olive oil", "vegetable oil", "avocado oil", "ghee", " oil "," oil$", "oil"]) \
       and not any(w in t for w in ["olive","pickle","oliv"]) :                return "Oils & Ghee"
    if "oil" in t and not any(w in t for w in ["pickle","olive"]):             return "Oils & Ghee"
    if any(w in t for w in ["bean", "lentil", "chickpea", "fava", "chori", "cowpea",
                              "kidney", "lima", "adzuki", "pea", "haleem", "bajella",
                              "white beans", "baked beans", "processed peas"]):
                                                                                return "Beans & Pulses"
    if any(w in t for w in ["rice", "basmati", "barley", "corn meal", "corn flour",
                              "corn grits", "whole corn", "wheat", "ugali", "corn"]):
                                                                                return "Rice & Grains"
    if any(w in t for w in ["vermicelli", "breadstick"]):                      return "Pasta & Noodles"
    if any(w in t for w in ["cheese", "nabulsi"]):                             return "Dairy & Cheese"
    if any(w in t for w in ["pickle", "pickled", "giardinera", "hot pepper"]) \
       and "olive" not in t:                                                   return "Pickles & Olives"
    if any(w in t for w in ["olive", "olives"]):                               return "Pickles & Olives"
    if any(w in t for w in ["walnut", "almond", "sesame", "raisin", "peanut",
                              "sunflower", "seed", "nut "]):                   return "Nuts & Seeds"
    if any(w in t for w in ["spice", "seasoning", "stock powder", "stock",
                              "marinade", "emulsion", "tahini", "halawa",
                              "lemon", "molasses"]):                           return "Spices & Herbs"
    if any(w in t for w in ["sauce", "salsa", "topping", "caramel",
                              "grape leaves", "syrup"]) \
       and "vimto" not in t:                                                   return "Condiments & Sauces"
    if any(w in t for w in ["tea", "juice", "drink", "water", "nectar",
                              "vimto", "barbican", "freez", "shani", "jannat",
                              "ulker tea", "chocolate", "hot choc", "malt"]):  return "Beverages"
    if any(w in t for w in ["chip", "biscuit", "cookie", "candy", "croissant",
                              "flan", "finger biscuit", "dolci"]):             return "Snacks & Sweets"
    return "General"

PREFIX_MAP = {
    "Beans & Pulses":    "BEAN",
    "Rice & Grains":     "GRAIN",
    "Oils & Ghee":       "OIL",
    "Beverages":         "BEV",
    "Snacks & Sweets":   "SNACK",
    "Nuts & Seeds":      "NUT",
    "Dairy & Cheese":    "DAIRY",
    "Spices & Herbs":    "SPICE",
    "Pickles & Olives":  "PICKLE",
    "Pasta & Noodles":   "PASTA",
    "Condiments & Sauces": "COND",
    "Charcoal":          "CHAR",
    "General":           "GEN",
}
counters = {}
def next_code(group):
    prefix = PREFIX_MAP.get(group, "ITEM")
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}-{counters[prefix]:04d}"


# ── 1. Load Excel ─────────────────────────────────────────────────────────────
print("=== [1] Loading Excel ===")
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx",
                             read_only=True, data_only=True)
ws = wb.active
rows_raw = list(ws.iter_rows(values_only=True))
headers  = [str(h).replace("\n", " ").strip() if h else "" for h in rows_raw[0]]

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

    xl_rows.append({"brand": brand, "desc": desc, "size": size,
                    "upc": upc, "cases": cases, "per_case": per_case,
                    "our_cost": our_cost})

print(f"  {len(xl_rows)} product rows")

# Detect duplicate brand+desc → append size to name for those
from collections import Counter
name_counts = Counter(f"{r['brand']}|{r['desc']}" for r in xl_rows)
for r in xl_rows:
    key = f"{r['brand']}|{r['desc']}"
    base_name = f"{r['brand']} {r['desc']}".strip()
    r["item_name"] = f"{base_name} {r['size']}".strip() if name_counts[key] > 1 else base_name
    r["item_group"] = get_item_group(r["brand"], r["desc"])
    r["item_code"]  = next_code(r["item_group"])


# ── 2. Items already deleted via _ssm_delete_all_items.py ────────────────────
print("\n=== [2] Items already cleared ===")
print("  (run _ssm_delete_all_items.py beforehand)")


# ── 3. Create items ───────────────────────────────────────────────────────────
print(f"\n=== [3] Creating {len(xl_rows)} items ===")
created = failed = 0
failed_items = []

for r in xl_rows:
    item_payload = {
        "doctype":      "Item",
        "item_code":    r["item_code"],
        "item_name":    r["item_name"],
        "item_group":   r["item_group"],
        "brand":        r["brand"] or None,
        "stock_uom":    "Nos",
        "is_stock_item": 1,
        "standard_rate": r["our_cost"],
        "package_size":  r["size"] or None,
        "items_per_case": str(r["per_case"]) if r["per_case"] else None,
        "cases_on_hand": r["cases"],
    }
    if r["upc"]:
        item_payload["barcodes"] = [{"barcode": r["upc"], "barcode_type": ""}]

    resp = s.post(f"{URL}/api/resource/Item", json=item_payload, timeout=30)
    if resp.status_code in (200, 201):
        created += 1
    elif r["upc"] and ("barcode" in resp.text.lower() or "already use" in resp.text.lower()):
        # Retry without barcode
        item_payload.pop("barcodes", None)
        resp2 = s.post(f"{URL}/api/resource/Item", json=item_payload, timeout=30)
        if resp2.status_code in (200, 201):
            created += 1
        else:
            failed_items.append((r["item_code"], r["item_name"], resp2.text[:120]))
            failed += 1
    else:
        failed_items.append((r["item_code"], r["item_name"], resp.text[:120]))
        failed += 1

    if (created + failed) % 50 == 0:
        print(f"  {created} created, {failed} failed...")

print(f"\n  Created : {created}")
print(f"  Failed  : {failed}")
if failed_items:
    print("  Failed items:")
    for code, name, err in failed_items[:10]:
        print(f"    {code}: {name[:40]} — {err[:80]}")


# ── 4. Summary by group ───────────────────────────────────────────────────────
print("\n=== [4] Summary by item group ===")
from collections import defaultdict
by_group = defaultdict(int)
for r in xl_rows:
    by_group[r["item_group"]] += 1
for g, cnt in sorted(by_group.items()):
    print(f"  {g:30} {cnt:3} items")

print("\nDONE — refresh Inventory Manager to see the repopulated catalogue.")
