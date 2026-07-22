"""
One-off: creates Atlas Lakes' own funding source in Dwolla sandbox
(the account that receives customer ACH debits and pays vendor ACH credits).

Uses Dwolla's sandbox test bank account values — no real bank involved.

Run once:
    DWOLLA_KEY=... DWOLLA_SECRET=... python setup_dwolla_master_account.py

Prints the resulting funding source URL — save it as
DWOLLA_MASTER_FUNDING_SOURCE_URL in .env / PaymentsSecret.
"""

import os
import sys
import requests

KEY = os.environ.get("DWOLLA_KEY")
SECRET = os.environ.get("DWOLLA_SECRET")
API_ROOT = "https://api-sandbox.dwolla.com"

if not KEY or not SECRET:
    print("Set DWOLLA_KEY and DWOLLA_SECRET in the environment first.")
    sys.exit(1)

token_resp = requests.post(
    "https://api-sandbox.dwolla.com/token",
    auth=(KEY, SECRET),
    data={"grant_type": "client_credentials"},
    timeout=15,
)
if token_resp.status_code != 200:
    print(f"Token request failed ({token_resp.status_code}): {token_resp.text}")
    print(f"KEY length={len(KEY)!r} SECRET length={len(SECRET)!r}")
    sys.exit(1)
access_token = token_resp.json()["access_token"]

s = requests.Session()
s.headers["Authorization"] = f"Bearer {access_token}"
s.headers["Accept"] = "application/vnd.dwolla.v1.hal+json"
s.headers["Content-Type"] = "application/vnd.dwolla.v1.hal+json"

root = s.get(f"{API_ROOT}/", timeout=15)
root.raise_for_status()
account_url = root.json()["_links"]["account"]["href"]
print(f"Dwolla account: {account_url}")

# Dwolla sandbox test bank values (per Dwolla docs) — always succeed verification.
resp = s.post(
    f"{API_ROOT}/funding-sources",
    json={
        "routingNumber": "222222226",
        "accountNumber": "123456789",
        "bankAccountType": "checking",
        "name": "Atlas Lakes Operating Account",
        "_links": {"account": {"href": account_url}},
    },
    timeout=15,
)
if resp.status_code != 201:
    print(f"Failed ({resp.status_code}): {resp.text}")
    sys.exit(1)

funding_source_url = resp.headers["Location"]
print(f"\nDWOLLA_MASTER_FUNDING_SOURCE_URL={funding_source_url}")
