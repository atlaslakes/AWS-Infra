"""One-off: verifies PLAID_CLIENT_ID/PLAID_SECRET work against Plaid sandbox."""

import os
import sys
import requests

CLIENT_ID = os.environ.get("PLAID_CLIENT_ID")
SECRET = os.environ.get("PLAID_SECRET")

if not CLIENT_ID or not SECRET:
    print("Set PLAID_CLIENT_ID and PLAID_SECRET in the environment first.")
    sys.exit(1)

resp = requests.post(
    "https://sandbox.plaid.com/link/token/create",
    json={
        "client_id": CLIENT_ID,
        "secret": SECRET,
        "client_name": "Atlas Lakes ACH Setup Check",
        "user": {"client_user_id": "setup-check"},
        "products": ["auth"],
        "country_codes": ["US"],
        "language": "en",
    },
    timeout=15,
)
if resp.status_code != 200:
    print(f"Failed ({resp.status_code}): {resp.text}")
    sys.exit(1)

print("Plaid sandbox credentials OK.")
print(f"link_token: {resp.json()['link_token']}")
