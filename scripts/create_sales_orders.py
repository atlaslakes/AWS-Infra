dimport requests
from datetime import date, timedelta

ERPNEXT_URL = "http://atlaslakeserp"
S = requests.Session()
S.headers.update({"Authorization": "token 647f56b706a1bea:6c615d3ea8cbd4d"})

price_lists = {"Pangea-A": 0.80, "Pangea-B": 0.85, "Pangea-C": 0.90, "Retail": 1.00}
customers = [
    {"name": "Pangea A",         "price_list": "Pangea-A"},
    {"name": "Pangea B",         "price_list": "Pangea-B"},
    {"name": "Pangea C",         "price_list": "Pangea-C"},
    {"name": "Walk-in Customer", "price_list": "Retail"},
]

r = S.get(f"{ERPNEXT_URL}/api/resource/Item",
          params={"fields": '["item_code","item_name","standard_rate"]', "limit_page_length": 5},
          timeout=15)
sample_items = r.json()["data"][:3]
today = str(date.today())
delivery_date = str(date.today() + timedelta(days=7))

for c in customers:
    mult = price_lists[c["price_list"]]
    items_payload = [{
        "doctype": "Sales Order Item",
        "item_code": i["item_code"],
        "item_name": i["item_name"],
        "qty": 10,
        "rate": round((float(i.get("standard_rate") or 0) or 10.0) * mult, 2),
        "delivery_date": delivery_date,
    } for i in sample_items]

    resp = S.post(f"{ERPNEXT_URL}/api/resource/Sales Order", json={
        "doctype": "Sales Order",
        "customer": c["name"],
        "transaction_date": today,
        "delivery_date": delivery_date,
        "selling_price_list": c["price_list"],
        "currency": "USD",
        "set_warehouse": "Stores - LD",
        "items": items_payload,
    }, timeout=20)

    if resp.status_code in (200, 201):
        print(f"SO created for {c['name']}: {resp.json()['data']['name']}")
    else:
        print(f"FAILED {c['name']}: {resp.text[:300]}")
