import requests

base = "http://3.216.86.193"
api_key = "647f56b706a1bea"
api_secret = "6c615d3ea8cbd4d"
invoice_name = "ACC-SINV-2026-00007"
format_name = "Atlas Invoice Classic"

session = requests.Session()
session.headers.update({"Authorization": f"token {api_key}:{api_secret}"})

resp = session.get(
    f"{base}/printview",
    params={
        "doctype": "Sales Invoice",
        "name": invoice_name,
        "format": format_name,
        "no_letterhead": 0,
        "_lang": "en",
    },
    timeout=30,
)
resp.raise_for_status()
html = resp.text

for key in [
    "inv-wrap",
    "Invoice #",
    "Product",
    "Price Per Piece",
    "Grand Total",
    "Outstanding",
    "Bill To",
    "Ship To",
]:
    idx = html.find(key)
    print(f"\nKEY: {key} | index={idx}")
    if idx != -1:
        start = max(0, idx - 260)
        end = min(len(html), idx + 420)
        print(html[start:end].replace("\n", " "))
