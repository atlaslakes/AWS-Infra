"""
Manage the Dwolla webhook subscription that feeds POST /webhooks/dwolla.

Nothing else in the repo creates it — without it, transfers initiate but never
reconcile into ERPNext Payment Entries. Dwolla also *pauses* a subscription
after ~200 consecutive delivery failures; this script un-pauses it.

Usage (reads DWOLLA_KEY / DWOLLA_SECRET / DWOLLA_ENV from .env):

    python scripts/setup/setup_dwolla_webhook.py --list
    python scripts/setup/setup_dwolla_webhook.py --url https://abc.execute-api.us-east-1.amazonaws.com/dev
    python scripts/setup/setup_dwolla_webhook.py --url <api-base> --rotate     # delete + recreate (new secret)
    python scripts/setup/setup_dwolla_webhook.py --url <api-base> --delete

The webhook path (/webhooks/dwolla) is appended automatically. The subscription
secret is taken from DWOLLA_WEBHOOK_SECRET and must match the value in
PaymentsSecret.dwolla_webhook_secret that the Lambda verifies against.
"""

import argparse
import base64
import os
import sys
from pathlib import Path

import requests

requests.packages.urllib3.disable_warnings()

DWOLLA_HOSTS = {
    "sandbox": "https://api-sandbox.dwolla.com",
    "production": "https://api.dwolla.com",
}
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


def dwolla_token(host, key, secret):
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
    ap.add_argument("--url", help="Payments API base URL (…/dev or …/prod); /webhooks/dwolla is appended")
    ap.add_argument("--list", action="store_true", help="list existing subscriptions and exit")
    ap.add_argument("--rotate", action="store_true", help="delete the matching subscription and recreate it")
    ap.add_argument("--delete", action="store_true", help="delete the matching subscription and exit")
    args = ap.parse_args()

    key = os.environ.get("DWOLLA_KEY")
    secret = os.environ.get("DWOLLA_SECRET")
    env = (os.environ.get("DWOLLA_ENV") or "sandbox").lower()
    hook_secret = os.environ.get("DWOLLA_WEBHOOK_SECRET")
    if not key or not secret:
        sys.exit("Set DWOLLA_KEY and DWOLLA_SECRET (in .env)")
    host = DWOLLA_HOSTS.get(env) or sys.exit(f"DWOLLA_ENV={env!r} not sandbox/production")

    tok = dwolla_token(host, key, secret)
    h = {**HAL, "Authorization": f"Bearer {tok}"}

    subs = requests.get(f"{host}/webhook-subscriptions", headers=h, timeout=30).json()
    existing = subs.get("_embedded", {}).get("webhook-subscriptions", [])

    if args.list:
        if not existing:
            print("No webhook subscriptions.")
        for s in existing:
            print(f"  {s['id']}  paused={s.get('paused')}  {s.get('url')}")
        return

    target_url = None
    if args.url:
        target_url = args.url.rstrip("/")
        if not target_url.endswith("/webhooks/dwolla"):
            target_url += "/webhooks/dwolla"

    match = None
    if target_url:
        match = next((s for s in existing if s.get("url") == target_url), None)
    elif len(existing) == 1:
        match = existing[0]

    if args.delete:
        if not match:
            sys.exit("No matching subscription to delete (pass --url).")
        r = requests.delete(f"{host}/webhook-subscriptions/{match['id']}", headers=h, timeout=30)
        print(f"deleted {match['id']}: {r.status_code}")
        return

    if match and args.rotate:
        requests.delete(f"{host}/webhook-subscriptions/{match['id']}", headers=h, timeout=30)
        print(f"deleted {match['id']} (rotate)")
        match = None

    if not target_url:
        sys.exit("Pass --url to create/ensure a subscription.")
    if not hook_secret:
        sys.exit("Set DWOLLA_WEBHOOK_SECRET (must match PaymentsSecret.dwolla_webhook_secret).")

    if match:
        if match.get("paused"):
            r = requests.post(f"{host}/webhook-subscriptions/{match['id']}",
                              headers=h, json={"paused": False}, timeout=30)
            print(f"un-paused {match['id']}: {r.status_code}")
        else:
            print(f"subscription already active: {match['id']}  {target_url}")
        print("NOTE: the secret can't be read back — use --rotate if you changed DWOLLA_WEBHOOK_SECRET.")
        return

    r = requests.post(f"{host}/webhook-subscriptions", headers=h,
                      json={"url": target_url, "secret": hook_secret}, timeout=30)
    if r.status_code != 201:
        sys.exit(f"create failed {r.status_code}: {r.text[:400]}")
    print(f"created: {r.headers.get('Location')}")
    print(f"  url    : {target_url}")
    print(f"  env    : {env}")


if __name__ == "__main__":
    main()
