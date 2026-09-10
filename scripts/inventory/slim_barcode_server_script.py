"""
Slim the "Auto Barcode Image on Item Save" Server Script down to barcode
value/type NORMALIZATION only -- it no longer generates custom_barcode_image.

Why: the old hook hand-rolled an SVG barcode in the Frappe sandbox (no
python-barcode import available). wkhtmltopdf renders those SVG data-URIs
unreliably (thin/merged bars, no digits) so a lot of invoices showed unscannable
barcodes, and every item save clobbered the good PNGs produced by
regenerate_barcode_images.py. Image generation is now a deliberate batch step
(scripts/inventory/regenerate_barcode_images.py); this hook keeps doing the
cheap, render-independent part: on save, normalise the first barcode row's value
and set barcode_type by length.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python slim_barcode_server_script.py [--show]
"""

import os
import sys
import requests
import urllib3
urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
SCRIPT_NAME = "Auto Barcode Image on Item Save"

SLIM_SCRIPT = '''# Normalise the first barcode row's value + barcode_type on save.
# Does NOT touch custom_barcode_image -- that's regenerated in batch by
# scripts/inventory/regenerate_barcode_images.py.

if doc.get("barcodes"):
\trow = doc.barcodes[0]
\tv = (row.barcode or "").strip()
\tif v[:1] == "*":
\t\tv = v[1:]

\tnorm_value = None
\tbtype = None

\tif v and v.isdigit():
\t\tn = len(v)
\t\tif n == 12:
\t\t\tnorm_value = v
\t\t\tbtype = "UPC"
\t\telif n == 11:
\t\t\tnorm_value = "0" + v
\t\t\tbtype = "UPC"
\t\telif n == 13:
\t\t\tnorm_value = v
\t\t\tbtype = "EAN"
\t\telif n == 8:
\t\t\tnorm_value = v
\t\t\tbtype = "EAN-8"
\t\telif n == 14:
\t\t\tnorm_value = v
\t\t\tbtype = "GS1"
\t\telif n == 15 and v[:1] == "1":
\t\t\tnorm_value = v[1:]
\t\t\tbtype = "GS1"
\t\telif n == 16 and v[:2] == "01":
\t\t\tnorm_value = v[2:]
\t\t\tbtype = "GS1"

\tif norm_value:
\t\tif row.barcode != norm_value or row.barcode_type != btype:
\t\t\trow.barcode = norm_value
\t\t\trow.barcode_type = btype
\t\t\tdoc.custom_barcode = norm_value
'''


def main():
    pwd = os.environ.get("ERP_ADMIN_PWD")
    if not pwd:
        sys.exit("Set ERP_ADMIN_PWD (and optionally ERP_ADMIN_USER).")
    s = requests.Session()
    s.verify = False
    r = s.post(f"{URL}/api/method/login",
               data={"usr": os.environ.get("ERP_ADMIN_USER", "Administrator"), "pwd": pwd}, timeout=15)
    if r.status_code != 200:
        sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")

    cur = s.get(f"{URL}/api/resource/Server Script/{requests.utils.quote(SCRIPT_NAME)}", timeout=20)
    if cur.status_code != 200:
        sys.exit(f"Server Script '{SCRIPT_NAME}' not found ({cur.status_code}).")
    d = cur.json()["data"]
    print(f"current: event={d.get('doctype_event')} disabled={d.get('disabled')} "
          f"len(script)={len(d.get('script') or '')}")

    if "--show" in sys.argv:
        print("\n--- current script ---\n" + (d.get("script") or ""))
        print("\n--- proposed slim script ---\n" + SLIM_SCRIPT)
        return

    r = s.put(f"{URL}/api/resource/Server Script/{requests.utils.quote(SCRIPT_NAME)}",
              json={"script": SLIM_SCRIPT, "disabled": 0}, timeout=25)
    if r.status_code not in (200, 201):
        sys.exit(f"update failed {r.status_code}: {r.text[:400]}")
    print(f"updated: len(script) now {len(r.json()['data'].get('script') or '')}")
    print("Image generation removed. Run regenerate_barcode_images.py to refresh images.")


if __name__ == "__main__":
    main()
