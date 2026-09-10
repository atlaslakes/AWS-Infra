"""
Bulk-update Item cost from a CSV, and immediately re-derive Selling Price
from each item's existing margin — without waiting for the per-minute
"Sync Item Stock And Price - Scheduled" job.

Why this exists: Item.valuation_rate is recomputed every minute from the
weighted-average of Bin.actual_qty * Bin.valuation_rate (see
setup_stock_price_scheduled_sync.py). Writing Item.valuation_rate directly
for an in-stock item gets silently overwritten on the next run. The only
durable way to change cost for an in-stock item is to change the stock
ledger itself via a Stock Reconciliation (valuation-only adjustment: same
qty, new rate). For an out-of-stock item (qty <= 0 in every warehouse) the
scheduled job has nothing to compute from, so a direct Item.valuation_rate
write is safe and durable.

CSV format (header required):
    item_code,cost
    ABC123,4.25
    XYZ999,11.90

Usage:
    ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python bulk_update_item_cost.py path/to/costs.csv [--warehouse "Stores - AL"]
"""

import os, sys, csv, argparse, requests
import urllib3; urllib3.disable_warnings()

PROD_URL = "https://erpnext.karavanimports.com"
PRICE_LIST = "Standard Selling"


def erp_login():
    user = os.environ.get("ERP_ADMIN_USER", "Administrator")
    pwd = os.environ.get("ERP_ADMIN_PWD")
    if not pwd:
        sys.exit("Set ERP_ADMIN_PWD (and optionally ERP_ADMIN_USER) before running.")
    s = requests.Session()
    s.verify = False
    r = s.post(f"{PROD_URL}/api/method/login", data={"usr": user, "pwd": pwd}, timeout=15)
    if r.status_code != 200:
        sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")
    return s


def get_bin_qty(s, item_code, warehouse):
    r = s.get(f"{PROD_URL}/api/resource/Bin", params={
        "filters": f'[["item_code","=","{item_code}"],["warehouse","=","{warehouse}"]]',
        "fields": '["actual_qty"]',
        "limit_page_length": 1,
    }, timeout=15)
    r.raise_for_status()
    data = r.json().get("data", [])
    return float(data[0]["actual_qty"]) if data else 0.0


def submit_stock_reconciliation(s, item_code, warehouse, qty, new_cost):
    doc = {
        "doctype": "Stock Reconciliation",
        "purpose": "Stock Reconciliation",
        "items": [{
            "item_code": item_code,
            "warehouse": warehouse,
            "qty": qty,
            "valuation_rate": new_cost,
        }],
    }
    r = s.post(f"{PROD_URL}/api/method/frappe.client.submit", json={"doc": doc}, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Stock Reconciliation failed: {r.status_code} {r.text[:300]}")


def get_margin(s, item_code):
    r = s.get(f"{PROD_URL}/api/resource/Pricing Rule/Margin - {item_code}", timeout=15)
    if r.status_code != 200:
        return "Percentage", 0.0
    d = r.json()["data"]
    return d.get("margin_type") or "Percentage", float(d.get("margin_rate_or_amount") or 0)


def upsert_item_price(s, item_code, new_price):
    r = s.get(f"{PROD_URL}/api/resource/Item Price", params={
        "filters": f'[["item_code","=","{item_code}"],["price_list","=","{PRICE_LIST}"]]',
        "fields": '["name"]',
        "limit_page_length": 1,
    }, timeout=15)
    r.raise_for_status()
    existing = r.json().get("data", [])
    if existing:
        s.put(f"{PROD_URL}/api/resource/Item Price/{existing[0]['name']}",
              json={"price_list_rate": new_price}, timeout=15).raise_for_status()
    else:
        s.post(f"{PROD_URL}/api/resource/Item Price", json={
            "item_code": item_code, "price_list": PRICE_LIST,
            "selling": 1, "price_list_rate": new_price,
        }, timeout=15).raise_for_status()


def update_one(s, item_code, cost, warehouse):
    qty = get_bin_qty(s, item_code, warehouse)
    if qty > 0:
        submit_stock_reconciliation(s, item_code, warehouse, qty, cost)
    else:
        r = s.put(f"{PROD_URL}/api/resource/Item/{item_code}",
                   json={"valuation_rate": cost}, timeout=15)
        r.raise_for_status()

    margin_type, margin_val = get_margin(s, item_code)
    new_price = cost * (1 + margin_val / 100) if margin_type == "Percentage" else cost + margin_val
    upsert_item_price(s, item_code, new_price)
    return new_price


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="?", help="CSV with item_code,cost columns (bulk mode)")
    ap.add_argument("--item", help="Single item code (individual mode)")
    ap.add_argument("--cost", type=float, help="New cost for --item (individual mode)")
    ap.add_argument("--warehouse", default="Stores - AL")
    args = ap.parse_args()

    if not args.csv_path and not (args.item and args.cost is not None):
        sys.exit("Provide either a csv_path (bulk) or --item CODE --cost N (individual).")

    s = erp_login()

    if args.item:
        try:
            new_price = update_one(s, args.item.strip(), args.cost, args.warehouse)
            print(f"ok: {args.item}  cost={args.cost}  price={new_price:.2f}")
        except Exception as e:
            sys.exit(f"FAIL: {args.item}  {e}")
        return

    ok, failed = 0, []
    with open(args.csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        item_code = row["item_code"].strip()
        cost = float(row["cost"])
        try:
            new_price = update_one(s, item_code, cost, args.warehouse)
            print(f"  ok: {item_code}  cost={cost}  price={new_price:.2f}")
            ok += 1
        except Exception as e:
            print(f"  FAIL: {item_code}  {e}")
            failed.append(item_code)

    print(f"\nDone. {ok} updated, {len(failed)} failed.")
    if failed:
        print("Failed items:", ", ".join(failed))


if __name__ == "__main__":
    main()
