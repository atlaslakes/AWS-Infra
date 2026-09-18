import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.auth import check_caller
from common.config import stripe_config, erpnext_config
from common.stripe_client import get_stripe_client, get_or_create_customer, create_setup_intent
from common.erpnext_client import ERPNextClient

_PARTY_DOCTYPES = {"Customer": "Customer", "Supplier": "Supplier"}


def handler(event, context):
    """POST /setup-intent
    Body: {"party_doctype": "Customer" | "Supplier", "party_id": "<ERPNext name>",
           "email": "...", "name": "..."}
    Called by Base44 right before launching Stripe Elements for a party who
    wants to save a card or bank account for auto-pay/Pay Now. The client
    confirms the returned SetupIntent directly with Stripe.js; there is no
    server-side token exchange step (unlike the old Plaid Link flow).
    """
    deny = check_caller(event)
    if deny:
        return deny

    body = json.loads(event.get("body") or "{}")
    party_doctype = body.get("party_doctype")
    party_id = body.get("party_id")
    if party_doctype not in _PARTY_DOCTYPES:
        return {"statusCode": 400, "body": json.dumps({"error": "party_doctype must be Customer or Supplier"})}
    if not party_id:
        return {"statusCode": 400, "body": json.dumps({"error": "party_id is required"})}

    stripe_cfg = stripe_config()
    client = get_stripe_client(stripe_cfg["secret_key"])

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])
    party = erp.get(party_doctype, party_id)
    if party is None:
        return {"statusCode": 404, "body": json.dumps({"error": f"{party_doctype} {party_id} not found"})}

    email = (body.get("email") or party.get("email_id") or "").strip()
    if not email:
        return {"statusCode": 400, "body": json.dumps({"error": "email is required to create the Stripe Customer"})}

    customer_id = get_or_create_customer(
        client,
        email=email,
        name=body.get("name", party_id),
        party_doctype=party_doctype,
        party_id=party_id,
        existing_customer_id=party.get("custom_stripe_customer_id"),
    )
    if customer_id != party.get("custom_stripe_customer_id"):
        erp.update(party_doctype, party_id, {"custom_stripe_customer_id": customer_id})

    setup_intent = create_setup_intent(client, customer_id=customer_id)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "client_secret": setup_intent.client_secret,
            "publishable_key": stripe_cfg["publishable_key"],
        }),
    }
