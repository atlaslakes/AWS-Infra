import requests
import json

ERPNEXT_URL = "http://atlaslakeserp"
S = requests.Session()
S.headers.update({"Authorization": "token 647f56b706a1bea:6c615d3ea8cbd4d"})

print("=== Existing Pricing Rules ===")
r = S.get(f"{ERPNEXT_URL}/api/resource/Pricing Rule", params={"fields": '["*"]'}, timeout=15)
if r.status_code == 200:
    rules = r.json().get("data", [])
    for rule in rules:
        print(f"Rule: {rule.get('name')} | Enabled: {rule.get('enabled')} | For Price List: {rule.get('for_price_list')} | Discount: {rule.get('discount_percentage')}%")
else:
    print(f"Failed to fetch Pricing Rules: {r.status_code} - {r.text}")

print("\n=== Existing Price Lists ===")
r = S.get(f"{ERPNEXT_URL}/api/resource/Price List", params={"fields": '["*"]'}, timeout=15)
if r.status_code == 200:
    pls = r.json().get("data", [])
    for pl in pls:
        print(f"Price List: {pl.get('name')} | Selling: {pl.get('selling')}")
else:
    print(f"Failed to fetch Price Lists: {r.status_code} - {r.text}")
