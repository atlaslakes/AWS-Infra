import os
"""Show exactly which Excel row maps to which ERPNext item, for California Garden items."""
import requests, openpyxl, re
from difflib import SequenceMatcher
requests.packages.urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

def norm(v):
    if not v: return ""
    v = str(v).lower().strip()
    v = re.sub(r"[^\w\s]", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def to_grams(value, unit):
    unit = unit.lower().strip()
    conv = {"g":1,"gr":1,"gram":1,"grams":1,"kg":1000,"oz":28.3495,"oz.":28.3495,
            "ounce":28.3495,"ounces":28.3495,"lb":453.592,"lbs":453.592,
            "pound":453.592,"pounds":453.592,"ml":1,"l":1000,"liter":1000,"litre":1000}
    return value * conv.get(unit, 0) if unit in conv else None

SIZE_RE = re.compile(r"([\d.]+)\s*([a-z\s]+)", re.I)

def sizes_match(a, b, tol=0.06):
    if norm(a) == norm(b): return True
    def parse(v):
        m = SIZE_RE.match(str(v).strip())
        if not m: return None
        return to_grams(float(m.group(1)), m.group(2).strip())
    ga, gb = parse(a), parse(b)
    if ga and gb:
        return abs(ga - gb) / max(ga, gb) <= tol
    return False

def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()

# Load Excel
wb = openpyxl.load_workbook(r"aws-infra\Karavan Inventory-updated.xlsx", read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
headers = [str(h).replace("\n", " ").strip() if h else "" for h in rows[0]]
xl_items = []
for row in rows[1:]:
    d = dict(zip(headers, row))
    brand = str(d.get("Brand") or "").strip()
    desc  = str(d.get("Description") or "").strip()
    size  = str(d.get("Size") or "").strip()
    cases = 0
    for k, v in d.items():
        if "cases" in k.lower() and "hand" in k.lower():
            try: cases = float(v) if v else 0
            except: cases = 0
    if brand or desc:
        xl_items.append({"brand": brand, "desc": desc, "size": size, "cases": cases})

# Load ERPNext items
r = s.get(f"{URL}/api/resource/Item",
          params={"fields": '["name","item_name","brand","package_size","items_per_case"]',
                  "limit": 500}, timeout=30)
erp_items = r.json().get("data", [])
for item in erp_items:
    brand = (item.get("brand") or "").strip()
    iname = (item.get("item_name") or "").strip()
    desc  = iname[len(brand):].strip() if brand and iname.lower().startswith(brand.lower()) else iname
    item["_desc"]  = desc
    item["_brand"] = brand
    item["_size"]  = (item.get("package_size") or "").strip()

# Show matches for California Garden 450g items
print(f"{'Code':<14} {'ERP Description':<45} -> {'XL Description':<45} {'Cases':>6}  {'Score':.3}")
print("-"*130)
for item in sorted(erp_items, key=lambda x: x["name"]):
    if "california" not in item["_brand"].lower():
        continue
    best_score, best = 0, None
    for x in xl_items:
        if norm(item["_brand"]) != norm(x["brand"]):
            continue
        if not sizes_match(item["_size"], x["size"]):
            continue
        score = sim(item["_desc"], x["desc"])
        if score < 0.5:
            continue
        if score > best_score:
            best_score, best = score, x
    if best:
        print(f"{item['name']:<14} {item['_desc']:<45} -> {best['desc']:<45} {best['cases']:>6.1f}  {best_score:.3f}")
    else:
        print(f"{item['name']:<14} {item['_desc']:<45} -> {'NO MATCH':<45}")
