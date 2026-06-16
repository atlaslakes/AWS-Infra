import json
import requests

BASE = "http://3.216.86.193"
API_KEY = "647f56b706a1bea"
API_SECRET = "6c615d3ea8cbd4d"

S = requests.Session()
S.headers.update({
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json",
    "Accept": "application/json",
})

# Minimal probes to inspect validation errors.
probes = [
    ("Purchase Order", {"doctype": "Purchase Order", "supplier": "", "items": []}),
    ("Sales Order", {"doctype": "Sales Order", "customer": "", "items": []}),
]

for doctype, payload in probes:
    r = S.post(f"{BASE}/api/resource/{doctype}", data=json.dumps(payload), timeout=45)
    print("\n===", doctype, "===")
    print("status:", r.status_code)
    print(r.text[:4000])

# Also print global defaults and one record each to derive valid values.
for path in [
    "/api/resource/Global Defaults/Global Defaults",
    "/api/resource/Company?fields=[\"name\",\"default_currency\",\"default_letter_head\"]&limit_page_length=5",
    "/api/resource/Supplier?fields=[\"name\"]&limit_page_length=3",
    "/api/resource/Customer?fields=[\"name\"]&limit_page_length=3",
    "/api/resource/Warehouse?fields=[\"name\",\"is_group\"]&filters=[[\"is_group\",\"=\",0]]&limit_page_length=5",
    "/api/resource/Price List?fields=[\"name\",\"enabled\",\"buying\",\"selling\",\"currency\"]&limit_page_length=20",
]:
    r = S.get(BASE + path, timeout=45)
    print("\n---", path, "---")
    print("status:", r.status_code)
    print(r.text[:4000])
