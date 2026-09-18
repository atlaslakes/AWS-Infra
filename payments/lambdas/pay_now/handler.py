import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.auth import check_caller
from common.config import stripe_config, erpnext_config
from common.stripe_client import get_stripe_client, get_or_create_customer, create_payment_intent
from common.erpnext_client import ERPNextClient

_INVOICE_TYPES = {
    "Sales Invoice": "customer",
    "Purchase Invoice": "supplier",
}
_PARTY_DOCTYPE = {"Sales Invoice": "Customer", "Purchase Invoice": "Supplier"}


def handler(event, context):
    """POST /pay-now
    Body: {"invoice_doctype": "Sales Invoice" | "Purchase Invoice", "invoice_name": "<ERPNext name>"}
    Called by Base44 when a customer/supplier clicks "Pay Now" on an invoice —
    an on-demand, one-time payment that doesn't require a saved payment method.
    Returns a client_secret for the frontend to confirm via Stripe.js. This
    Lambda never writes the invoice's payment status directly — only the
    stripe-webhook handler does that, once Stripe confirms the charge actually
    succeeded.
    """
    deny = check_caller(event)
    if deny:
        return deny

    body = json.loads(event.get("body") or "{}")
    invoice_doctype = body.get("invoice_doctype")
    invoice_name = body.get("invoice_name")

    if invoice_doctype not in _INVOICE_TYPES:
        return {"statusCode": 400, "body": json.dumps({"error": "invoice_doctype must be Sales Invoice or Purchase Invoice"})}
    if not invoice_name:
        return {"statusCode": 400, "body": json.dumps({"error": "invoice_name is required"})}

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])

    invoice = erp.get(invoice_doctype, invoice_name)
    if invoice is None:
        return {"statusCode": 404, "body": json.dumps({"error": f"{invoice_doctype} {invoice_name} not found"})}

    amount = float(invoice.get("outstanding_amount") or 0)
    if amount <= 0:
        return {"statusCode": 400, "body": json.dumps({"error": "invoice has no outstanding amount"})}

    party_field = _INVOICE_TYPES[invoice_doctype]
    party_doctype = _PARTY_DOCTYPE[invoice_doctype]
    party_id = invoice[party_field]
    party = erp.get(party_doctype, party_id)
    if party is None:
        return {"statusCode": 404, "body": json.dumps({"error": f"{party_doctype} {party_id} not found"})}

    email = (party.get("email_id") or "").strip()
    if not email:
        return {"statusCode": 400, "body": json.dumps({"error": "party has no email on file"})}

    stripe_cfg = stripe_config()
    client = get_stripe_client(stripe_cfg["secret_key"])

    customer_id = get_or_create_customer(
        client,
        email=email,
        name=party_id,
        party_doctype=party_doctype,
        party_id=party_id,
        existing_customer_id=party.get("custom_stripe_customer_id"),
    )
    if customer_id != party.get("custom_stripe_customer_id"):
        erp.update(party_doctype, party_id, {"custom_stripe_customer_id": customer_id})

    currency = (invoice.get("currency") or "usd").lower()
    payment_intent = create_payment_intent(
        client,
        customer_id=customer_id,
        amount_cents=round(amount * 100),
        currency=currency,
        payment_method_types=["card", "us_bank_account"],
        metadata={"invoice_doctype": invoice_doctype, "invoice_name": invoice_name},
        idempotency_key=f"payintent:{invoice_doctype}:{invoice_name}",
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "client_secret": payment_intent.client_secret,
            "publishable_key": stripe_cfg["publishable_key"],
        }),
    }
