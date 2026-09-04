"""
Corrects Item Price (Standard Selling) rows where the per-bottle/per-unit
retail price was mistakenly entered as if it were the case price.

Background: on this system, Item.stock_uom is "Nos" for every item, and by
convention "1 Nos" == "1 case" -- that's how qty/rate are recorded on Sales
Orders/Invoices (see _fix_invoice_pdf_upc_qty_layout.py's Price/Case
column, which renders Sales Invoice Item.rate directly as the case price).
For a subset of items, someone entered the per-piece price into that same
"Standard Selling" price list slot instead, e.g. OIL-0002 (AlGhazal Ghee,
12/case) was priced at $5.66 -- a plausible per-bottle price, but nonsense
as a 12-bottle case price, and it showed up wrong on a real invoice
(ACC-SINV-2026-00123) as a result.

Detection: flag items where items_per_case > 1 and the Standard Selling
price is below the item's cost (valuation_rate, falling back to
last_purchase_rate) -- cost comes from actual purchase transactions so
it's trusted over a manually-typed sales price. Fix: multiply the price by
items_per_case to restore the case price.

Two items where that multiply still lands at/under cost were excluded
after manual review (something else is wrong with them, not a simple
per-piece/per-case mixup) and are NOT touched by this script:
  - SPICE-0066 (Maggi bouillon): x24 only reaches $1.20 vs $4.31 cost
  - GRAIN-0032 (Jannat Yellow Burgul #2): x12 reaches $22.92 vs $23.00 cost,
    zero margin

Full candidate list (all 138, including the 2 excluded) is saved at
data/price_review_case_vs_piece_2026-08-21.csv for reference.

This does NOT touch already-submitted Sales Invoices/Orders -- those keep
whatever rate was recorded at the time. Confirmed explicitly not to amend
ACC-SINV-2026-00123.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python _fix_per_piece_prices_entered_as_case_price.py [--dry-run]
"""

import os, sys, csv, json
import requests
import urllib3; urllib3.disable_warnings()

URL = "https://erpnext.karavanimports.com"
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "price_review_case_vs_piece_2026-08-21.csv")
EXCLUDE = {"SPICE-0066", "GRAIN-0032"}


def main():
    dry_run = "--dry-run" in sys.argv
    user = os.environ.get("ERP_ADMIN_USER", "Administrator")
    pwd = os.environ.get("ERP_ADMIN_PWD")
    if not pwd:
        sys.exit("Set ERP_ADMIN_PWD (and optionally ERP_ADMIN_USER) before running.")

    with open(CSV_PATH, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["item_code"] not in EXCLUDE]
    print(f"Items to update: {len(rows)} (excluded: {sorted(EXCLUDE)})")

    if dry_run:
        for r in rows[:10]:
            print(f"  {r['item_code']}: {r['current_price']} -> {r['proposed_price']}")
        print("  ...")
        print("\n--dry-run set, not writing changes.")
        return

    s = requests.Session()
    s.verify = False
    r = s.post(f"{URL}/api/method/login", data={"usr": user, "pwd": pwd}, timeout=15)
    if r.status_code != 200:
        sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")

    ok, fail = 0, 0
    for row in rows:
        resp = s.post(
            f"{URL}/api/method/frappe.client.set_value",
            json={
                "doctype": "Item Price",
                "name": row["price_row_name"],
                "fieldname": "price_list_rate",
                "value": float(row["proposed_price"]),
            },
            timeout=20,
        )
        if resp.status_code in (200, 201):
            ok += 1
        else:
            fail += 1
            print(f"  FAIL {row['item_code']} ({row['price_row_name']}): {resp.status_code} {resp.text[:200]}")

    print(f"\nUpdated: {ok}  Failed: {fail}")


if __name__ == "__main__":
    main()
