import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import plaid_config, dwolla_config, erpnext_config
from common.plaid_client import get_plaid_client, exchange_public_token, create_dwolla_processor_token
from common.dwolla_client import get_dwolla_client, create_customer, attach_funding_source_from_plaid
from common.erpnext_client import ERPNextClient

_PARTY_DOCTYPES = {"Customer": "Customer", "Supplier": "Supplier"}


def handler(event, context):
    """POST /exchange-and-attach
    Body: {
      "party_doctype": "Customer" | "Supplier",
      "party_id": "<ERPNext name>",
      "public_token": "<Plaid public_token>",
      "account_id": "<Plaid account_id for the chosen bank account>",
      "email": "<party email, needed to create the Dwolla Customer if none exists>",
      "first_name": "...", "last_name": "..."
    }
    Called by Base44 once Plaid Link succeeds. Exchanges the public token,
    creates/reuses a Dwolla Customer for this party, attaches the verified
    bank account as a Dwolla funding source, and stores the resulting IDs
    back onto the ERPNext Customer/Supplier record.
    """
    body = json.loads(event.get("body") or "{}")
    party_doctype = body.get("party_doctype")
    party_id = body.get("party_id")
    public_token = body.get("public_token")
    account_id = body.get("account_id")

    if party_doctype not in _PARTY_DOCTYPES:
        return {"statusCode": 400, "body": json.dumps({"error": "party_doctype must be Customer or Supplier"})}
    if not all([party_id, public_token, account_id]):
        return {"statusCode": 400, "body": json.dumps({"error": "party_id, public_token, account_id are required"})}

    plaid_cfg = plaid_config()
    plaid_client = get_plaid_client(plaid_cfg["client_id"], plaid_cfg["secret"], plaid_cfg["environment"])
    access_token, item_id = exchange_public_token(plaid_client, public_token)
    processor_token = create_dwolla_processor_token(plaid_client, access_token=access_token, account_id=account_id)

    dwolla_cfg = dwolla_config()
    dwolla_client = get_dwolla_client(dwolla_cfg["key"], dwolla_cfg["secret"], dwolla_cfg["environment"])

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])
    party = erp.get(party_doctype, party_id)
    if party is None:
        return {"statusCode": 404, "body": json.dumps({"error": f"{party_doctype} {party_id} not found"})}

    customer_url = party.get("custom_dwolla_customer_id")
    if not customer_url:
        customer_url = create_customer(
            dwolla_client,
            first_name=body.get("first_name", party_doctype),
            last_name=body.get("last_name", party_id),
            email=body["email"],
        )

    funding_source_url = attach_funding_source_from_plaid(
        dwolla_client, customer_url, processor_token=processor_token, name=f"{party_doctype} {party_id} bank account"
    )

    erp.update(party_doctype, party_id, {
        "custom_dwolla_customer_id": customer_url,
        "custom_dwolla_funding_source_id": funding_source_url,
        "custom_bank_linked": 1,
        "custom_plaid_item_id": item_id,
    })

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "linked"}),
    }
