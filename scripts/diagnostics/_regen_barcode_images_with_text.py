"""
Regenerates every Item.custom_barcode_image with the human-readable UPC/EAN
digits baked into the barcode graphic itself (python-barcode's write_text),
instead of the bars-only image setup_barcode_images.py originally produced.

Why: the "Atlas Invoice Tracking Classic" print format was rendering the
bars-only image with a separately-positioned <span> of the barcode number
underneath it. On a real invoice printout that read as two loosely related
pieces (bars floating above a small offset number) rather than a normal
UPC-A label, where the digits sit directly under/between the bars as part
of one graphic. Baking the text into the image itself (standard
python-barcode behavior) fixes that at the source, and also makes the
overall barcode graphic noticeably bigger/more legible, per request.

Same generation logic as setup_barcode_images.py (see that file for the
symbology-selection rules) -- this only changes the ImageWriter options.
The print format (see _fix_invoice_pdf_upc_qty_layout.py) is updated
alongside this to stop rendering the separate number span when an image is
present, since the number is now part of the image.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python _regen_barcode_images_with_text.py [--dry-run]
"""

import os, sys, json, base64, io
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3; urllib3.disable_warnings()

import barcode
from barcode.writer import ImageWriter

URL = "https://erpnext.karavanimports.com"
WORKERS = 8


def make_session(user, pwd):
    s = requests.Session()
    s.verify = False
    r = s.post(f"{URL}/api/method/login", data={"usr": user, "pwd": pwd}, timeout=15)
    if r.status_code != 200:
        sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")
    return s


def fetch_item(session, name):
    r = session.get(f"{URL}/api/resource/Item/{requests.utils.quote(name)}", timeout=20)
    if r.status_code != 200:
        return name, None
    return name, r.json().get("data", {})


def pick_symbology(value, barcode_type):
    value = (value or "").strip()
    if barcode_type == "UPC" and len(value) == 12 and value.isdigit():
        return "upca", value
    if barcode_type == "EAN" and len(value) == 13 and value.isdigit():
        return "ean13", value
    if not barcode_type:
        if len(value) == 12 and value.isdigit():
            return "upca", value
        if len(value) == 13 and value.isdigit():
            return "ean13", value
    return None, None


def generate_data_uri(symbology, value):
    writer = ImageWriter()
    cls = barcode.get_barcode_class(symbology)
    bc = cls(value, writer=writer)
    buf = io.BytesIO()
    # write_text=True bakes the human-readable digits under the bars as
    # part of the same image (standard UPC-A/EAN-13 label look), instead of
    # the print format having to render a separate text element next to it.
    # module_height/font_size bumped up so the baked-in text stays legible
    # at the larger on-invoice display size the print format now uses.
    bc.write(buf, options={
        "write_text": True,
        "quiet_zone": 2.0,
        "module_height": 12.0,
        "font_size": 8,
        "text_distance": 3.0,
    })
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def main():
    dry_run = "--dry-run" in sys.argv
    user = os.environ.get("ERP_ADMIN_USER", "Administrator")
    pwd = os.environ.get("ERP_ADMIN_PWD")
    if not pwd:
        sys.exit("Set ERP_ADMIN_PWD (and optionally ERP_ADMIN_USER) before running.")

    s = make_session(user, pwd)

    r = s.get(
        f"{URL}/api/resource/Item",
        params={
            "filters": json.dumps([["custom_barcode", "!=", ""]]),
            "fields": json.dumps(["name"]),
            "limit_page_length": 0,
        },
        timeout=30,
    )
    names = [d["name"] for d in r.json().get("data", [])]
    print(f"Items with custom_barcode: {len(names)}")

    to_write = {}  # name -> data_uri
    skipped = []
    fetch_fail = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_item, s, name) for name in names]
        done = 0
        for fut in as_completed(futures):
            name, data = fut.result()
            done += 1
            if done % 50 == 0:
                print(f"  scanned {done}/{len(names)}...")
            if data is None:
                fetch_fail += 1
                continue
            value = data.get("custom_barcode") or ""
            rows = data.get("barcodes") or []
            barcode_type = (rows[0].get("barcode_type") or "").strip() if rows else ""
            symbology, clean_value = pick_symbology(value, barcode_type)
            if not symbology:
                skipped.append((name, value))
                continue
            try:
                to_write[name] = generate_data_uri(symbology, clean_value)
            except Exception as e:
                skipped.append((name, f"{value} ({e})"))

    print(f"\nFetch failures: {fetch_fail}")
    print(f"Skipped (no valid UPC/EAN): {len(skipped)}")
    for name, value in skipped[:30]:
        print(f"  skip {name}: {value}")
    print(f"To generate + push: {len(to_write)}")

    if dry_run:
        print("\n--dry-run set, not writing changes.")
        return

    ok, fail = 0, 0
    for name, data_uri in to_write.items():
        resp = s.post(
            f"{URL}/api/method/frappe.client.set_value",
            json={"doctype": "Item", "name": name, "fieldname": "custom_barcode_image", "value": data_uri},
            timeout=20,
        )
        if resp.status_code in (200, 201):
            ok += 1
        else:
            fail += 1
            print(f"  FAIL {name}: {resp.status_code} {resp.text[:200]}")

    print(f"\nUpdated: {ok}  Failed: {fail}")


if __name__ == "__main__":
    main()
