import datetime
import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.auth import check_caller
from common.config import stripe_config, erpnext_config
from common.stripe_client import get_stripe_client, retrieve_setup_intent, retrieve_mandate
from common.erpnext_client import ERPNextClient

_PARTY_DOCTYPES = {"Customer": "Customer", "Supplier": "Supplier"}


def handler(event, context):
    """POST /attach-payment-method
    Body: {
      "party_doctype": "Customer" | "Supplier",
      "party_id": "<ERPNext name>",
      "setup_intent_id": "<Stripe SetupIntent id>",
    }
    Called by Base44 once Stripe.js confirms the SetupIntent client-side. We
    never trust the client's reported status — the SetupIntent is retrieved
    server-side and its status/payment_method/mandate read from there before
    anything is written back onto the ERPNext party.
    """
    deny = check_caller(event)
    if deny:
        return deny

    body = json.loads(event.get("body") or "{}")
    party_doctype = body.get("party_doctype")
    party_id = body.get("party_id")
    setup_intent_id = body.get("setup_intent_id")

    if party_doctype not in _PARTY_DOCTYPES:
        return {"statusCode": 400, "body": json.dumps({"error": "party_doctype must be Customer or Supplier"})}
    if not all([party_id, setup_intent_id]):
        return {"statusCode": 400, "body": json.dumps({"error": "party_id and setup_intent_id are required"})}

    stripe_cfg = stripe_config()
    client = get_stripe_client(stripe_cfg["secret_key"])

    setup_intent = retrieve_setup_intent(client, setup_intent_id)
    if setup_intent.status != "succeeded":
        return {"statusCode": 400, "body": json.dumps({"error": f"setup_intent status is {setup_intent.status!r}, not succeeded"})}

    payment_method_id = setup_intent.payment_method
    payment_method = client.PaymentMethod.retrieve(payment_method_id)
    method_type = "Bank" if payment_method.type == "us_bank_account" else "Card"

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])
    party = erp.get(party_doctype, party_id)
    if party is None:
        return {"statusCode": 404, "body": json.dumps({"error": f"{party_doctype} {party_id} not found"})}

    updates = {
        "custom_stripe_customer_id": setup_intent.customer,
        "custom_stripe_payment_method_id": payment_method_id,
        "custom_payment_method_type": method_type,
    }

    if method_type == "Bank":
        mandate_id = setup_intent.mandate
        mandate_active = False
        if mandate_id:
            mandate = retrieve_mandate(client, mandate_id)
            mandate_active = mandate.status == "active"
            updates["custom_stripe_mandate_id"] = mandate_id
            if mandate_active:
                updates["custom_ach_authorization_date"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        updates["custom_bank_linked"] = 1 if mandate_active else 0
    else:
        updates["custom_card_on_file"] = 1

    erp.update(party_doctype, party_id, updates)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "status": "linked",
            "payment_method_type": method_type,
        }),
    }
