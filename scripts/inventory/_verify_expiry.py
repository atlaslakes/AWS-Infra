import os
import requests
requests.packages.urllib3.disable_warnings()

INSTANCES = {
    "PROD":    "https://www.karavanimports.com",
    "STAGING": "http://3.216.86.193",
}
PASS = os.environ.get("ERP_ADMIN_PWD")

def uq(v): return requests.utils.quote(str(v), safe="")

checks = {
    "DocType: Item Expiry Shipment":   ("DocType",        "Item Expiry Shipment"),
    "Custom Field: expiry_date":       ("Custom Field",   "Stock Entry Detail-expiry_date"),
    "Server Script: submit hook":      ("Server Script",  "Karavan-Stock-Entry-Expiry"),
    "Server Script: daily scheduler":  ("Server Script",  "Karavan Daily Expiry Check"),
    "Client Script: Stock Entry":      ("Client Script",  "Karavan-Expiry-StockEntry"),
    "Client Script: Sales Invoice":    ("Client Script",  "Karavan-Expiry-SalesInvoice"),
}

for label, url in INSTANCES.items():
    s = requests.Session(); s.verify = False
    s.post(f"{url}/api/method/login", data={"usr":"Administrator","pwd":PASS}, timeout=15)
    print(f"\n{label} ({url})")
    for desc, (resource, name) in checks.items():
        r = s.get(f"{url}/api/resource/{resource.replace(' ','%20')}/{uq(name)}", timeout=10)
        status = "OK" if r.status_code == 200 else "MISSING"
        print(f"  {'[OK]' if status=='OK' else '[--]'}  {desc}")
