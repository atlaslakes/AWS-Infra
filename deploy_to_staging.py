import os
"""
Deploys all Karavan customizations from production to staging instance.
  Production : https://www.karavanimports.com
  Staging    : http://3.216.86.193

Applies:
  1. Invoice print format "Atlas Invoice Tracking Classic"
  2. Inventory Manager script report
  3. Stock Settings (no negative stock, default warehouse, update_stock default)
  4. Property Setter: Sales Invoice update_stock = 1 by default
  5. Company contact info
"""
import requests, json, sys

requests.packages.urllib3.disable_warnings()

PROD = "https://www.karavanimports.com"
STAG = "http://3.216.86.193"
PASS = os.environ.get("ERP_ADMIN_PWD")

def session(url):
    s = requests.Session(); s.verify = False
    r = s.post(f"{url}/api/method/login",
               data={"usr": "Administrator", "pwd": PASS}, timeout=20)
    assert r.json().get("message") == "Logged In", f"Login failed at {url}: {r.text[:100]}"
    return s

def uq(v):
    return requests.utils.quote(str(v), safe="")

print("Connecting...")
prod = session(PROD)
stag = session(STAG)
print("  Both instances connected.\n")

# ── 1. Invoice Print Format ────────────────────────────────────────────────────
print("[1] Copying Print Format...")
pf = prod.get(f"{PROD}/api/resource/Print%20Format/Atlas%20Invoice%20Tracking%20Classic",
              timeout=20).json().get("data", {})
html = pf.get("html", "")
if not html:
    print("  ERROR: could not read HTML from production"); sys.exit(1)

# Check if print format exists on staging
check = stag.get(f"{STAG}/api/resource/Print%20Format/Atlas%20Invoice%20Tracking%20Classic",
                 timeout=15)
if check.status_code == 200:
    r = stag.put(f"{STAG}/api/resource/Print%20Format/Atlas%20Invoice%20Tracking%20Classic",
                 json={"html": html}, timeout=30)
    print(f"  Updated: {r.status_code}")
else:
    r = stag.post(f"{STAG}/api/resource/Print%20Format",
                  json={
                      "doc_type":       "Sales Invoice",
                      "print_format_type": "Jinja",
                      "name":           "Atlas Invoice Tracking Classic",
                      "standard":       "No",
                      "module":         "Accounts",
                      "html":           html,
                  }, timeout=30)
    print(f"  Created: {r.status_code}")
if r.status_code not in (200, 201):
    print("  WARN:", r.text[:200])

# ── 2. Inventory Manager Script Report ────────────────────────────────────────
print("\n[2] Copying Inventory Manager report...")
rpt = prod.get(f"{PROD}/api/resource/Report/Inventory%20Manager", timeout=20).json().get("data", {})
report_payload = {
    "report_name":  "Inventory Manager",
    "ref_doctype":  "Item",
    "report_type":  "Script Report",
    "is_standard":  "No",
    "module":       "Stock",
    "script":       rpt.get("script", ""),
    "filters":      rpt.get("filters", "[]"),
}
rc = stag.get(f"{STAG}/api/resource/Report/Inventory%20Manager", timeout=15)
if rc.status_code == 200:
    r2 = stag.put(f"{STAG}/api/resource/Report/Inventory%20Manager",
                  json=report_payload, timeout=20)
    print(f"  Updated: {r2.status_code}")
else:
    r2 = stag.post(f"{STAG}/api/resource/Report", json=report_payload, timeout=20)
    print(f"  Created: {r2.status_code}")
if r2.status_code not in (200, 201):
    print("  WARN:", r2.text[:200])

# ── 3. Detect company + warehouse on staging ───────────────────────────────────
print("\n[3] Detecting staging company & warehouse...")
companies = stag.get(f"{STAG}/api/resource/Company",
                     params={"fields": '["name","abbr"]', "limit": 10}, timeout=15
                     ).json().get("data", [])
# prefer "Lakes" company; fallback to first non-demo
company = next((c["name"] for c in companies if c["name"].lower() == "lakes"), None) or \
          next((c["name"] for c in companies if "demo" not in c["name"].lower()), companies[0]["name"])
abbr = next(c["abbr"] for c in companies if c["name"] == company)
print(f"  Company: {company} ({abbr})")

warehouses = stag.get(f"{STAG}/api/resource/Warehouse",
                      params={"fields": '["name","is_group","warehouse_type"]', "limit": 50},
                      timeout=15).json().get("data", [])
store_wh = next((w["name"] for w in warehouses
                 if not w.get("is_group") and
                 w.get("warehouse_type") not in ("Transit",) and
                 "transit" not in w["name"].lower() and
                 abbr in w["name"]), None)
print(f"  Warehouse: {store_wh}")

# ── 4. Stock Settings ──────────────────────────────────────────────────────────
print("\n[4] Applying Stock Settings...")
ss_body = {"allow_negative_stock": 0}
if store_wh:
    ss_body["default_warehouse"] = store_wh
r3 = stag.put(f"{STAG}/api/resource/Stock%20Settings/Stock%20Settings",
              json=ss_body, timeout=20)
print(f"  allow_negative_stock=0, default_warehouse={store_wh}: {r3.status_code}")

# ── 5. Property Setter: update_stock = 1 default ──────────────────────────────
print("\n[5] Setting Sales Invoice update_stock default...")
existing = stag.get(f"{STAG}/api/resource/Property%20Setter",
                    params={"filters": '[["doc_type","=","Sales Invoice"],["field_name","=","update_stock"],["property","=","default"]]',
                            "fields": '["name"]'}, timeout=15).json().get("data", [])
ps = {
    "doctype": "Property Setter", "doc_type": "Sales Invoice",
    "doctype_or_field": "DocField", "field_name": "update_stock",
    "property": "default", "property_type": "Check", "value": "1",
    "is_system_generated": 0,
}
if existing:
    r4 = stag.put(f"{STAG}/api/resource/Property%20Setter/{uq(existing[0]['name'])}",
                  json=ps, timeout=15)
    print(f"  Updated: {r4.status_code}")
else:
    r4 = stag.post(f"{STAG}/api/resource/Property%20Setter", json=ps, timeout=15)
    print(f"  Created: {r4.status_code}")

# ── 6. Company contact info ────────────────────────────────────────────────────
print("\n[6] Updating company contact info...")
r5 = stag.put(f"{STAG}/api/resource/Company/{uq(company)}",
              json={
                  "email": "accounting@karavanimports.com",
                  "phone_no": "",
                  "address": "8035 Ranchers Rd. NE, Fridley, MN 55432",
              }, timeout=15)
print(f"  {company}: {r5.status_code}")

print("\nDeployment complete.")
print(f"  Staging: {STAG}")
print(f"  Print format, Inventory Manager, Stock Settings all applied to '{company}'")
