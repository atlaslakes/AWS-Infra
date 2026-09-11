"""
Regenerate every Item.custom_barcode_image as a scannable PNG (base64 data-URI),
and CLEAR the field for items whose barcode can't be rendered as a linear symbol
(so the print format falls back to plain text instead of a broken image).

Supersedes setup_barcode_images.py + _regen_barcode_images_with_text.py, and
replaces the SVG output of the "Auto Barcode Image on Item Save" Server Script
(which should be slimmed to value/type normalization only -- see
slim_barcode_server_script.py). Three generators had been writing to this field
and none cleaned up after the others; this one is the single source of truth.

Symbology, by the digit count of the normalized barcode value:
    8  -> EAN-8
   11  -> UPC-A   (python-barcode appends the check digit)
   12  -> UPC-A
   13  -> EAN-13
   14  -> ITF-14 / GTIN-14
   15 starting "1"  -> drop the leading digit -> 14 -> ITF-14
   16 starting "01" -> drop "01" -> 14 -> ITF-14
   anything else (non-numeric, other lengths, GS1-128 concat strings) -> no image

PNG options: digits baked into the graphic (write_text), full 6.5 mm quiet zone
(the old scripts used 2.0 mm -- below the UPC/EAN minimum and a scannability
risk), taller modules for legibility at invoice scale.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python regenerate_barcode_images.py [--dry-run] [--limit N]
"""

import base64
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
urllib3.disable_warnings()

import barcode
from barcode.writer import ImageWriter

URL = "https://erpnext.karavanimports.com"
WORKERS = 8

WRITE_OPTS = {
    "write_text": True,
    "module_height": 9.0,
    "module_width": 0.30,
    "font_size": 9,
    "text_distance": 3.0,
    "quiet_zone": 6.5,
}


def make_session(user, pwd):
    s = requests.Session()
    s.verify = False
    r = s.post(f"{URL}/api/method/login", data={"usr": user, "pwd": pwd}, timeout=15)
    if r.status_code != 200:
        sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")
    return s


def normalize(value):
    """Return (clean_value, symbology) or (None, None) if not renderable."""
    v = (value or "").strip()
    if v.startswith("*"):
        v = v[1:]
    if not v.isdigit():
        return None, None
    n = len(v)
    if n == 8:
        return v, "ean8"
    if n == 11 or n == 12:
        return v, "upca"
    if n == 13:
        return v, "ean13"
    if n == 14:
        return v, "ean14"
    if n == 15 and v[0] == "1":
        return v[1:], "ean14"
    if n == 16 and v[:2] == "01":
        return v[2:], "ean14"
    return None, None


def data_uri(symbology, value):
    cls = barcode.get_barcode_class(symbology)
    bc = cls(value, writer=ImageWriter())
    buf = io.BytesIO()
    bc.write(buf, options=WRITE_OPTS)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def fetch(session, name):
    r = session.get(f"{URL}/api/resource/Item/{requests.utils.quote(name)}", timeout=25)
    if r.status_code != 200:
        return name, None
    d = r.json().get("data", {})
    return name, {
        "barcode": (d.get("custom_barcode") or "").strip(),
        "image": d.get("custom_barcode_image") or "",
    }


def main():
    dry = "--dry-run" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    pwd = os.environ.get("ERP_ADMIN_PWD")
    if not pwd:
        sys.exit("Set ERP_ADMIN_PWD (and optionally ERP_ADMIN_USER).")
    s = make_session(os.environ.get("ERP_ADMIN_USER", "Administrator"), pwd)

    r = s.get(f"{URL}/api/resource/Item",
              params={"fields": json.dumps(["name"]), "limit_page_length": 0}, timeout=60)
    names = [d["name"] for d in r.json().get("data", [])]
    if limit:
        names = names[:limit]
    print(f"items: {len(names)}")

    regen = {}    # name -> new data-URI
    clear = []    # name -> image field should be emptied
    keep = 0
    genfail = []
    fetchfail = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(fetch, s, n) for n in names]
        for i, f in enumerate(as_completed(futs), 1):
            name, d = f.result()
            if i % 100 == 0:
                print(f"  scanned {i}/{len(names)}")
            if d is None:
                fetchfail += 1
                continue
            clean, sym = normalize(d["barcode"])
            if not sym:
                if d["image"]:
                    clear.append(name)
                continue
            try:
                uri = data_uri(sym, clean)
            except Exception as e:
                genfail.append((name, d["barcode"], str(e)))
                if d["image"]:
                    clear.append(name)
                continue
            if uri == d["image"]:
                keep += 1
            else:
                regen[name] = uri

    print(f"\nfetch failures : {fetchfail}")
    print(f"already correct: {keep}")
    print(f"to (re)generate: {len(regen)}")
    print(f"to clear (unrenderable barcode): {len(clear)}")
    print(f"generation errors: {len(genfail)}")
    for n, v, e in genfail[:20]:
        print(f"  genfail {n}: {v!r} -> {e}")

    if dry:
        print("\n--dry-run: no writes.")
        return

    ok = fail = 0
    for name, uri in regen.items():
        rp = s.post(f"{URL}/api/method/frappe.client.set_value",
                    json={"doctype": "Item", "name": name,
                          "fieldname": "custom_barcode_image", "value": uri}, timeout=25)
        ok += rp.status_code in (200, 201)
        fail += rp.status_code not in (200, 201)
    for name in clear:
        rp = s.post(f"{URL}/api/method/frappe.client.set_value",
                    json={"doctype": "Item", "name": name,
                          "fieldname": "custom_barcode_image", "value": ""}, timeout=25)
        ok += rp.status_code in (200, 201)
        fail += rp.status_code not in (200, 201)

    print(f"\nwrites ok: {ok}  failed: {fail}")


if __name__ == "__main__":
    main()
