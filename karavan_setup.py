import os
"""
Karavan Imports — Professional ERPNext Inventory Setup
=======================================================
1. Creates Item Groups (category hierarchy)
2. Creates all 85 Brands
3. Creates Custom Fields: "Items Per Case/Unit" + "Package Size" on Item
4. Imports all 271 items from CSV (with UPC barcodes)
5. Creates Opening Stock entry for on-hand quantities
"""

import requests, json, csv, time, re
from pathlib import Path
from collections import Counter

requests.packages.urllib3.disable_warnings()

PROD_URL = "https://www.karavanimports.com"
PASS     = os.environ.get("ERP_ADMIN_PWD")
CSV_PATH = Path(r"C:\Users\aizen\Desktop\AWS\aws-infra\Karavan Inventory - Sheet1.csv")

# ─── Category detection ───────────────────────────────────────────────────────
CATEGORIES = [
    ("Rice & Grains",       ["rice", "wheat", "barley", "corn", "bulgur", "couscous", "flour",
                              "semolina", "grits", "shelled wheat", "calrose"]),
    ("Pasta & Noodles",     ["pasta", "noodle", "spaghetti", "macaroni", "farfalle",
                              "chifferini", "shell pasta", "penne", "vermicelli"]),
    ("Spices & Herbs",      ["spice", "pepper", "cumin", "coriander", "cardamom", "cinnamon",
                              "turmeric", "sumac", "ginger", "anise", "cloves", "bay leave",
                              "fenugreek", "oregano", "dill", "seven spice", "7 spice",
                              "kufta", "falafel", "kabseh", "masala", "biryani", "hawaji",
                              "tandoori", "shawarma", "seasoning", "black seed", "citric acid",
                              "lemon pepper", "kabab", "steak"]),
    ("Oils & Ghee",         ["olive oil", "ghee", "vegetable oil", "avocado oil",
                              "sunflower oil", "oil blend"]),
    ("Pickles & Olives",    ["pickle", "pickled", "olive", "giardinera", "turnip"]),
    ("Beans & Pulses",      ["fava", "foul", "kidney bean", "white bean", "chickpea", "peas",
                              "bajela", "lentil", "black eye", "adzuki", "cowpea", "chori",
                              "split fava", "broad bean", "lima bean"]),
    ("Beverages",           ["juice", " drink", "water", "tea", "hot chocolate", "syrup",
                              "nectar", "smoothie", "sparkling", "vimto", "shani", "schweppes"]),
    ("Dairy & Cheese",      ["cheese", "milk", "cream", "puck", "nido"]),
    ("Nuts & Seeds",        ["almond", "walnut", "sesame", "sunflower seed", "raisin",
                              "pine nut", "sunflower seeds", "golden raisin"]),
    ("Snacks & Sweets",     ["biscuit", "candy", "mochi", "jelly", "jellies", "croissant",
                              "marshmallow", "halawa", "basbousa", "flan", "caramel",
                              "waffle syrup", "chocolate pie", "potato", "chips",
                              "finger biscuit", "tea biscuit", "tamarind"]),
    ("Condiments & Sauces", ["tahini", "tahina", "vinegar", "hot sauce", "bouillon",
                              "stock powder", "emulsion", "ginger garlic paste",
                              "tomato paste", "red chili paste", "orange blossom",
                              "rose water", "molasses", "salsa", "soup packet"]),
    ("Personal Care",       ["soap", "mask", "face"]),
    ("Charcoal",            ["charcoal", "mesquite"]),
]

def detect_category(description: str) -> str:
    d = description.lower()
    for cat, keywords in CATEGORIES:
        for kw in keywords:
            if kw in d:
                return cat
    return "General"

# ─── Barcode type detection ───────────────────────────────────────────────────
def barcode_type(upc: str) -> str:
    digits = re.sub(r"\D", "", upc)
    if len(digits) == 12:
        return "UPC-A"
    if len(digits) == 13:
        return "EAN"
    return "Code-128"

# ─── Item code generation ─────────────────────────────────────────────────────
_seen_codes: set = set()
_upc_counter = Counter()

def make_item_code(brand: str, description: str, size: str, upc: str) -> str:
    b = brand.strip()
    d = description.strip()
    sz = size.strip()
    u = upc.strip()

    if u:
        _upc_counter[u] += 1
        candidate = u if _upc_counter[u] == 1 else f"{u}-{_upc_counter[u]}"
        if candidate not in _seen_codes:
            _seen_codes.add(candidate)
            return candidate

    base = f"{b} - {d}" if b else d
    for c in [base, f"{base} ({sz})", f"{base} [{sz}]"]:
        if c not in _seen_codes:
            _seen_codes.add(c)
            return c
    i = 2
    while True:
        c = f"{base} #{i}"
        if c not in _seen_codes:
            _seen_codes.add(c)
            return c
        i += 1

# ─── HTTP session ─────────────────────────────────────────────────────────────
s = requests.Session()
s.verify = False

def login():
    r = s.post(f"{PROD_URL}/api/method/login",
               data={"usr": "Administrator", "pwd": PASS}, timeout=20)
    assert r.json().get("message") == "Logged In", r.text[:300]
    print("  Logged in to production")

def GET(path, **params):
    r = s.get(f"{PROD_URL}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def POST(path, body):
    return s.post(f"{PROD_URL}{path}", json=body, timeout=90)

def PUT(path, body):
    return s.put(f"{PROD_URL}{path}", json=body, timeout=90)

def uq(v):
    return requests.utils.quote(str(v), safe="")

def create_if_missing(doctype, name, payload):
    """PUT → 404 → POST."""
    r = PUT(f"/api/resource/{uq(doctype)}/{uq(name)}", payload)
    if r.status_code == 404:
        r = POST(f"/api/resource/{uq(doctype)}", {"name": name, **payload})
    return r

# ─── Main ─────────────────────────────────────────────────────────────────────
print("=" * 65)
print("  Karavan Imports — ERPNext Professional Inventory Setup")
print("=" * 65)
login()

# ── 1. Discover warehouse ──────────────────────────────────────────────────────
print("\n[1] Discovering warehouse ...")
wh_resp = GET("/api/resource/Warehouse",
              **{"fields": '["name","warehouse_name","is_group"]', "limit": 100})
warehouses = [w for w in wh_resp.get("data", []) if not w.get("is_group")]
warehouse = next(
    (w["name"] for w in warehouses
     if "store" in w.get("warehouse_name", "").lower()),
    warehouses[0]["name"] if warehouses else "Stores - KI"
)
print(f"   -> {warehouse}")

# ── 2. Item Groups ─────────────────────────────────────────────────────────────
print("\n[2] Creating Item Groups ...")
ITEM_GROUPS = [
    "Rice & Grains", "Pasta & Noodles", "Spices & Herbs", "Oils & Ghee",
    "Pickles & Olives", "Beans & Pulses", "Beverages", "Dairy & Cheese",
    "Nuts & Seeds", "Snacks & Sweets", "Condiments & Sauces",
    "Personal Care", "Charcoal", "General",
]
for ig in ITEM_GROUPS:
    r = create_if_missing("Item Group", ig, {
        "item_group_name": ig,
        "parent_item_group": "All Item Groups",
        "is_group": 0,
    })
    tag = "OK" if r.status_code in (200, 201) else f"skip({r.status_code})"
    print(f"   [{ig}] {tag}")
    time.sleep(0.05)

# ── 3. Read CSV ────────────────────────────────────────────────────────────────
print("\n[3] Reading CSV ...")
rows = []
with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        brand  = (row.get("Brand") or "").strip()
        desc   = (row.get("Description") or "").strip()
        upc    = (row.get("UPC") or "").strip()
        per_c  = (row.get("items Per Case/Unit") or "").strip()
        size   = (row.get("Size") or "").strip()
        try:
            qty = float((row.get("Cases On Hand") or "0").strip() or "0")
        except ValueError:
            qty = 0.0
        if not desc:
            continue
        rows.append({
            "brand": brand, "description": desc, "upc": upc,
            "qty": qty, "per_case": per_c, "size": size,
            "category": detect_category(desc),
        })
print(f"   {len(rows)} items loaded")

# ── 4. Brands ──────────────────────────────────────────────────────────────────
print("\n[4] Creating Brands ...")
brands = sorted(set(r["brand"] for r in rows if r["brand"]))
for brand in brands:
    r = create_if_missing("Brand", brand, {"brand": brand})
    tag = "OK" if r.status_code in (200, 201) else f"skip({r.status_code})"
    print(f"   [{brand}] {tag}")
    time.sleep(0.04)

# ── 5. Custom Fields ───────────────────────────────────────────────────────────
print("\n[5] Creating Custom Fields on Item ...")
CF = [
    {
        "name": "Item-items_per_case",
        "dt": "Item", "fieldname": "items_per_case",
        "label": "Items Per Case/Unit", "fieldtype": "Data",
        "insert_after": "stock_uom", "in_list_view": 1,
    },
    {
        "name": "Item-package_size",
        "dt": "Item", "fieldname": "package_size",
        "label": "Package Size", "fieldtype": "Data",
        "insert_after": "items_per_case", "in_list_view": 1,
    },
]
for cf in CF:
    r = create_if_missing("Custom Field", cf["name"], cf)
    tag = "OK" if r.status_code in (200, 201) else f"FAIL({r.status_code}): {r.text[:120]}"
    print(f"   [{cf['name']}] {tag}")

# ── 6. Import Items ────────────────────────────────────────────────────────────
print("\n[6] Importing Items ...")
ok = fail = 0
items_for_stock = []

for row in rows:
    code = make_item_code(row["brand"], row["description"], row["size"], row["upc"])
    name = f"{row['brand']} {row['description']}".strip() if row["brand"] else row["description"]
    desc_full = f"{row['description']} | {row['size']}" if row["size"] else row["description"]

    barcodes = ([{"barcode": row["upc"], "barcode_type": barcode_type(row["upc"])}]
                if row["upc"] else [])

    payload = {
        "item_code":      code,
        "item_name":      name,
        "item_group":     row["category"],
        "stock_uom":      "Nos",
        "is_stock_item":  1,
        "brand":          row["brand"] if row["brand"] else None,
        "description":    desc_full,
        "items_per_case": row["per_case"],
        "package_size":   row["size"],
        "barcodes":       barcodes,
    }

    r = POST("/api/resource/Item", payload)
    if r.status_code in (200, 201):
        action = "NEW"
    else:
        # Already exists — update
        r2 = PUT(f"/api/resource/Item/{uq(code)}", payload)
        if r2.status_code in (200, 201):
            action = "UPD"
            r = r2
        else:
            print(f"  ERR [{code[:55]}]: {r.status_code} {r.text[:80]}")
            fail += 1
            continue

    print(f"  {action} [{code[:60]}]")
    ok += 1
    if row["qty"] > 0:
        items_for_stock.append((code, row["qty"]))
    time.sleep(0.06)

print(f"\n   Items: {ok} OK, {fail} failed")
print(f"   {len(items_for_stock)} items with opening stock qty > 0")

# ── 7. Opening Stock ───────────────────────────────────────────────────────────
print("\n[7] Creating Opening Stock ...")

BATCH = 80   # items per Stock Entry

def submit_se(name):
    r = PUT(f"/api/resource/Stock%20Entry/{uq(name)}", {"docstatus": 1})
    return r.status_code in (200, 201)

batches = [items_for_stock[i:i+BATCH] for i in range(0, len(items_for_stock), BATCH)]
for bi, batch in enumerate(batches, 1):
    se_items = [
        {
            "item_code":  code,
            "t_warehouse": warehouse,
            "qty":         qty,
            "basic_rate":  0,
            "allow_zero_valuation_rate": 1,
        }
        for code, qty in batch
    ]
    payload = {
        "doctype":          "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "purpose":          "Opening Stock",
        "remarks":          f"Karavan Imports opening stock batch {bi}/{len(batches)}",
        "items":            se_items,
    }
    r = POST("/api/resource/Stock Entry", payload)
    if r.status_code in (200, 201):
        se_name = r.json().get("data", {}).get("name", "?")
        submitted = submit_se(se_name)
        status = "submitted" if submitted else f"DRAFT (submit {se_name} manually)"
        print(f"   Batch {bi}/{len(batches)}: {len(batch)} items -> {se_name} [{status}]")
    else:
        print(f"   Batch {bi} FAILED: {r.status_code} {r.text[:250]}")
    time.sleep(1)

print("\n" + "=" * 65)
print("  DONE. Check karavanimports.com -> Stock -> Items")
print("=" * 65)
