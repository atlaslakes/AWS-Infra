"""
Sets barcode_type = "UPC" on every existing Item Barcode row across all Items.

Background: Items already use ERPNext's native barcode system (the `barcodes`
child table on Item, doctype "Item Barcode" with fields `barcode` +
`barcode_type`) -- populated with real UPC/EAN values but `barcode_type` was
left blank. This script fills that in as "UPC" (one of the doctype's built-in
barcode_type select options, alongside "UPC-A", "EAN", etc.) so the barcode
metadata is correct for ERPNext's own scan-to-identify features.

Note: this does NOT put a scannable barcode *image* on the printed invoice --
that's a separate change to the "Atlas Invoice Tracking Classic" print format
(see scripts/diagnostics/_fix_invoice_pdf_footer_pagenum_carryover.py and the
planned barcode-image generation script). This script only fixes the
barcode_type metadata on the Item records themselves.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python set_barcode_type_upc.py [--dry-run]
"""

import os, sys, json, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
BARCODE_TYPE = "UPC"
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


def main():
    dry_run = "--dry-run" in sys.argv
    user = os.environ.get("ERP_ADMIN_USER", "Administrator")
    pwd = os.environ.get("ERP_ADMIN_PWD")
    if not pwd:
        sys.exit("Set ERP_ADMIN_PWD (and optionally ERP_ADMIN_USER) before running.")

    s = make_session(user, pwd)

    r = s.get(f"{URL}/api/resource/Item", params={"fields": '["name"]', "limit_page_length": 0}, timeout=30)
    all_items = [d["name"] for d in r.json().get("data", [])]
    print(f"Total items: {len(all_items)}")

    to_update = {}  # name -> updated barcodes list
    no_barcode = 0
    already_ok = 0
    fetch_fail = 0

    # Each worker needs its own session (requests.Session isn't thread-safe for cookies otherwise it's mostly fine to share, but use one shared session for simplicity)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_item, s, name) for name in all_items]
        done = 0
        for fut in as_completed(futures):
            name, data = fut.result()
            done += 1
            if done % 100 == 0:
                print(f"  scanned {done}/{len(all_items)}...")
            if data is None:
                fetch_fail += 1
                continue
            barcodes = data.get("barcodes") or []
            if not barcodes:
                no_barcode += 1
                continue
            needs_update = any((row.get("barcode_type") or "") != BARCODE_TYPE for row in barcodes)
            if not needs_update:
                already_ok += 1
                continue
            for row in barcodes:
                row["barcode_type"] = BARCODE_TYPE
            to_update[name] = barcodes

    print(f"\nNo barcode rows: {no_barcode}")
    print(f"Already {BARCODE_TYPE}: {already_ok}")
    print(f"Fetch failures: {fetch_fail}")
    print(f"To update: {len(to_update)}")

    if dry_run:
        print("\n--dry-run set, not writing changes.")
        for name in list(to_update)[:20]:
            print(" would update:", name)
        return

    ok, fail = 0, 0
    for name, barcodes in to_update.items():
        resp = s.put(
            f"{URL}/api/resource/Item/{requests.utils.quote(name)}",
            json={"barcodes": barcodes},
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
