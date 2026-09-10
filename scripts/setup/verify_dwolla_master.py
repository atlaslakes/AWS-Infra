"""
Verify Atlas Lakes' master Dwolla funding source.

setup_dwolla_master_account.py adds the business bank account by raw
routing/account number, which leaves it `unverified` — and Dwolla rejects every
transfer to/from an unverified funding source. This completes micro-deposit
verification.

Reads DWOLLA_KEY / DWOLLA_SECRET / DWOLLA_ENV / DWOLLA_MASTER_FUNDING_SOURCE_URL
from .env.

    python scripts/setup/verify_dwolla_master.py                 # status; auto-verify in sandbox
    python scripts/setup/verify_dwolla_master.py --init          # initiate micro-deposits (production)
    python scripts/setup/verify_dwolla_master.py --amounts 0.03 0.09   # complete with the real amounts

Production flow: run --init once, wait 1-2 business days for the two small
deposits to post to the bank, then run --amounts A B with those values.
Sandbox: micro-deposit amounts are always 0.01 / 0.01 and this script completes
the whole cycle in one run.
"""

import argparse
import base64
import os
import sys
import time
from pathlib import Path

import requests

requests.packages.urllib3.disable_warnings()

HOSTS = {"sandbox": "https://api-sandbox.dwolla.com", "production": "https://api.dwolla.com"}
HAL = {"Accept": "application/vnd.dwolla.v1.hal+json",
       "Content-Type": "application/vnd.dwolla.v1.hal+json"}


def load_dotenv():
    p = Path(__file__).resolve().parents[2] / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def token(host, key, secret):
    b = base64.b64encode(f"{key}:{secret}".encode()).decode()
    r = requests.post(f"{host}/token",
                      headers={"Authorization": f"Basic {b}",
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Dwolla token failed {r.status_code}: {r.text[:300]}")
    return r.json()["access_token"]


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="initiate micro-deposits and exit")
    ap.add_argument("--amounts", nargs=2, metavar=("A", "B"),
                    help="complete verification with the two deposit amounts, e.g. 0.03 0.09")
    args = ap.parse_args()

    key, secret = os.environ.get("DWOLLA_KEY"), os.environ.get("DWOLLA_SECRET")
    env = (os.environ.get("DWOLLA_ENV") or "sandbox").lower()
    fs = os.environ.get("DWOLLA_MASTER_FUNDING_SOURCE_URL")
    if not key or not secret:
        sys.exit("Set DWOLLA_KEY and DWOLLA_SECRET (in .env)")
    if not fs:
        sys.exit("Set DWOLLA_MASTER_FUNDING_SOURCE_URL (in .env)")
    host = HOSTS.get(env) or sys.exit(f"DWOLLA_ENV={env!r} not sandbox/production")
    h = {**HAL, "Authorization": f"Bearer {token(host, key, secret)}"}

    def status():
        r = requests.get(fs, headers=h, timeout=30)
        if r.status_code != 200:
            sys.exit(f"funding source lookup failed {r.status_code}: {r.text[:300]}")
        return r.json()

    j = status()
    print(f"master funding source: {j.get('name')!r}")
    print(f"  status : {j.get('status')}   removed: {j.get('removed')}   env: {env}")
    if j.get("status") == "verified":
        print("Already verified — nothing to do.")
        return

    def complete(a, b):
        r = requests.post(f"{fs}/micro-deposits", headers=h, json={
            "amount1": {"value": f"{float(a):.2f}", "currency": "USD"},
            "amount2": {"value": f"{float(b):.2f}", "currency": "USD"},
        }, timeout=30)
        if r.status_code not in (200, 201):
            sys.exit(f"verify failed {r.status_code}: {r.text[:400]}")
        print(f"verification submitted -> status={status().get('status')}")

    if args.amounts:
        complete(*args.amounts)
        return

    # initiate
    r = requests.post(f"{fs}/micro-deposits", headers=h, timeout=30)
    if r.status_code not in (200, 201):
        # 400 with 'already exists' just means they were initiated before.
        if "exists" not in r.text.lower():
            sys.exit(f"initiate micro-deposits failed {r.status_code}: {r.text[:400]}")
    print("micro-deposits initiated.")

    if env == "production" or args.init:
        print("\nProduction: wait 1-2 business days for two small deposits to post,")
        print("then run:  python scripts/setup/verify_dwolla_master.py --amounts <A> <B>")
        return

    # sandbox: clear + auto-complete (amounts are always 0.01 / 0.01)
    sim = requests.post(f"{host}/sandbox/simulations", headers=h, json={}, timeout=30)
    print(f"POST /sandbox/simulations -> {sim.status_code}"
          + ("" if sim.status_code in (200, 201, 202)
             else "  (simulator disabled on this account; verification may lag)"))
    time.sleep(2)
    complete("0.01", "0.01")


if __name__ == "__main__":
    main()
