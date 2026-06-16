import requests

BASE = "http://3.216.86.193"
API_KEY = "647f56b706a1bea"
API_SECRET = "6c615d3ea8cbd4d"
FORMAT_NAME = "Atlas Invoice Classic"
INVOICE_NAME = "ACC-SINV-2026-00007"

session = requests.Session()
session.headers.update({"Authorization": f"token {API_KEY}:{API_SECRET}"})

fmt_url = f"{BASE}/api/resource/Print Format/{requests.utils.quote(FORMAT_NAME)}"
get_resp = session.get(fmt_url, timeout=30)
get_resp.raise_for_status()
html = get_resp.json()["data"].get("html", "")

if ">UPC</th>" not in html:
    html = html.replace(
        '<th style="width:8%" class="text-right">Quantity</th>',
        '<th style="width:8%" class="text-right">Quantity</th>\n        <th style="width:15%">UPC</th>',
    )

if "row.barcode" not in html:
    html = html.replace(
        '<td class="text-right">{{ qty }}</td>',
        '<td class="text-right">{{ qty }}</td>\n        <td>{{ row.barcode or "-" }}</td>',
    )

put_resp = session.put(fmt_url, json={"html": html}, timeout=30)
put_resp.raise_for_status()

preview = session.get(
    f"{BASE}/printview",
    params={
        "doctype": "Sales Invoice",
        "name": INVOICE_NAME,
        "format": FORMAT_NAME,
        "no_letterhead": 0,
        "_lang": "en",
    },
    timeout=30,
)
preview.raise_for_status()
text = preview.text

print("Revert applied.")
print("UPC in preview:", "UPC" in text)
print("Price Per Piece index:", text.find("Price Per Piece"))
print("UPC index:", text.find("UPC"))
