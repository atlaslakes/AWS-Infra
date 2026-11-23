import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.auth import check_caller
from common.config import stripe_config, erpnext_config
from common.stripe_client import (
    get_stripe_client,
    get_or_create_customer,
    create_payment_intent,
    card_funding_from_confirmation_token,
    blocking_payment_intent,
)
from common.erpnext_client import ERPNextClient
from common import surcharge

_INVOICE_TYPES = {
    "Sales Invoice": "customer",
    "Purchase Invoice": "supplier",
}
_PARTY_DOCTYPE = {"Sales Invoice": "Customer", "Purchase Invoice": "Supplier"}
_METHOD_TYPES = ["card", "us_bank_account"]


def _resp(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


class _Fail(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.response = _resp(status, {"error": message})


def _load_invoice_and_party(erp, body):
    invoice_doctype = body.get("invoice_doctype")
    invoice_name = body.get("invoice_name")
    if invoice_doctype not in _INVOICE_TYPES:
        raise _Fail(400, "invoice_doctype must be Sales Invoice or Purchase Invoice")
    if not invoice_name:
        raise _Fail(400, "invoice_name is required")

    invoice = erp.get(invoice_doctype, invoice_name)
    if invoice is None:
        raise _Fail(404, f"{invoice_doctype} {invoice_name} not found")

    amount = float(invoice.get("outstanding_amount") or 0)
    if amount <= 0:
        raise _Fail(400, "invoice has no outstanding amount")

    party_doctype = _PARTY_DOCTYPE[invoice_doctype]
    party_id = invoice[_INVOICE_TYPES[invoice_doctype]]
    party = erp.get(party_doctype, party_id)
    if party is None:
        raise _Fail(404, f"{party_doctype} {party_id} not found")
    return invoice_doctype, invoice_name, invoice, party_doctype, party_id, party, round(amount * 100)


def _ensure_customer(client, erp, party_doctype, party_id, party):
    email = (party.get("email_id") or "").strip()
    if not email:
        raise _Fail(400, "party has no email on file")
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
    return customer_id


def _breakdown_for_token(client, erp, invoice_doctype, invoice, base_cents, token_id):
    token = client.ConfirmationToken.retrieve(token_id)
    method_type, funding, brand, last4 = card_funding_from_confirmation_token(token)
    if method_type not in _METHOD_TYPES:
        raise _Fail(400, f"unsupported payment method type {method_type!r}")
    state = surcharge.billing_state_for(erp, invoice) if invoice_doctype == "Sales Invoice" else None
    breakdown = surcharge.compute(base_cents, funding=funding, invoice_doctype=invoice_doctype, billing_state=state)
    breakdown.update({"payment_method_type": method_type, "card_brand": brand, "card_last4": last4})
    return breakdown


def _quote(body):
    """POST /pay-now/quote
    Body: {invoice_doctype, invoice_name, confirmation_token?}
    Without confirmation_token: returns the base amount + currency so the
    portal can mount the Payment Element in deferred-intent mode.
    With confirmation_token (from stripe.createConfirmationToken): returns the
    exact breakdown — base, credit-card surcharge (0 for debit/prepaid/bank),
    total — for the portal to show BEFORE the customer confirms."""
    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])
    invoice_doctype, invoice_name, invoice, *_rest, base_cents = _load_invoice_and_party(erp, body)
    currency = (invoice.get("currency") or "usd").lower()
    stripe_cfg = stripe_config()

    token_id = body.get("confirmation_token")
    if not token_id:
        return _resp(200, {
            "base_cents": base_cents,
            "currency": currency,
            "payment_method_types": _METHOD_TYPES,
            "credit_card_surcharge_rate": str(surcharge.surcharge_rate()) if invoice_doctype == "Sales Invoice" else "0",
            "publishable_key": stripe_cfg["publishable_key"],
        })

    client = get_stripe_client(stripe_cfg["secret_key"])
    breakdown = _breakdown_for_token(client, erp, invoice_doctype, invoice, base_cents, token_id)
    breakdown["currency"] = currency
    return _resp(200, breakdown)


def _confirm(body):
    """POST /pay-now/confirm
    Body: {invoice_doctype, invoice_name, confirmation_token}
    Recomputes the breakdown server-side (never trusts an amount from the
    client), then creates + confirms the PaymentIntent for the total. Returns
    status + client_secret; when status is "requires_action" (3-D Secure) the
    portal calls stripe.handleNextAction({clientSecret}). As before, ERPNext
    is only updated by the webhook once Stripe reports success."""
    token_id = body.get("confirmation_token")
    if not token_id:
        return _resp(400, {"error": "confirmation_token is required"})

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])
    invoice_doctype, invoice_name, invoice, party_doctype, party_id, party, base_cents = _load_invoice_and_party(erp, body)
    currency = (invoice.get("currency") or "usd").lower()

    stripe_cfg = stripe_config()
    client = get_stripe_client(stripe_cfg["secret_key"])

    blocking = blocking_payment_intent(client, erp, invoice_doctype, invoice_name)
    if blocking:
        return _resp(409, {"error": "a payment for this invoice is already in progress", "payment_intent_id": blocking})

    breakdown = _breakdown_for_token(client, erp, invoice_doctype, invoice, base_cents, token_id)
    customer_id = _ensure_customer(client, erp, party_doctype, party_id, party)

    try:
        payment_intent = _create_confirmed_intent(client, customer_id, currency, invoice_doctype, invoice_name, breakdown, token_id)
    except client.error.CardError as exc:
        # Declines are a normal customer-facing outcome, not a server error.
        return _resp(402, {"error": exc.user_message or "card declined", "decline_code": getattr(exc, "code", None)})

    breakdown.update({
        "currency": currency,
        "status": payment_intent.status,
        "client_secret": payment_intent.client_secret,
        "payment_intent_id": payment_intent.id,
    })
    return _resp(200, breakdown)


def _create_confirmed_intent(client, customer_id, currency, invoice_doctype, invoice_name, breakdown, token_id):
    return create_payment_intent(
        client,
        customer_id=customer_id,
        amount_cents=breakdown["total_cents"],
        currency=currency,
        payment_method_types=_METHOD_TYPES,
        confirm=True,
        confirmation_token=token_id,
        description=surcharge.describe(invoice_name, breakdown),
        metadata={
            "invoice_doctype": invoice_doctype,
            "invoice_name": invoice_name,
            "channel": "portal",
            "base_cents": str(breakdown["base_cents"]),
            "surcharge_cents": str(breakdown["surcharge_cents"]),
            "surcharge_rate": breakdown["surcharge_rate"],
            "card_funding": breakdown["funding"] or "",
        },
        # One PaymentIntent per confirmation token: a double-click / retry
        # of the same confirmation returns the same PaymentIntent.
        idempotency_key=f"paynow:{invoice_doctype}:{invoice_name}:{token_id}",
    )


def _legacy(body):
    """POST /pay-now (legacy, NO surcharge)
    Returns a client_secret for a PaymentIntent fixed at the outstanding
    amount. Kept only until the portal moves to /pay-now/quote + /confirm;
    set LEGACY_PAY_NOW=disabled afterwards so credit cards can't bypass the
    surcharge through this route."""
    if os.environ.get("LEGACY_PAY_NOW", "enabled") == "disabled":
        return _resp(410, {"error": "use /pay-now/quote and /pay-now/confirm"})

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])
    invoice_doctype, invoice_name, invoice, party_doctype, party_id, party, base_cents = _load_invoice_and_party(erp, body)

    stripe_cfg = stripe_config()
    client = get_stripe_client(stripe_cfg["secret_key"])
    customer_id = _ensure_customer(client, erp, party_doctype, party_id, party)

    currency = (invoice.get("currency") or "usd").lower()
    payment_intent = create_payment_intent(
        client,
        customer_id=customer_id,
        amount_cents=base_cents,
        currency=currency,
        payment_method_types=_METHOD_TYPES,
        metadata={"invoice_doctype": invoice_doctype, "invoice_name": invoice_name},
        idempotency_key=f"payintent:{invoice_doctype}:{invoice_name}",
    )
    return _resp(200, {
        "client_secret": payment_intent.client_secret,
        "publishable_key": stripe_cfg["publishable_key"],
    })


def handler(event, context):
    """Routes: POST /pay-now (legacy), POST /pay-now/quote, POST /pay-now/confirm.
    All require the Base44 shared secret."""
    deny = check_caller(event)
    if deny:
        return deny

    try:
        body = json.loads(event.get("body") or "{}")
    except ValueError:
        return _resp(400, {"error": "body must be JSON"})

    path = (event.get("rawPath") or event.get("routeKey") or "").rstrip("/")
    try:
        if path.endswith("/pay-now/quote"):
            return _quote(body)
        if path.endswith("/pay-now/confirm"):
            return _confirm(body)
        return _legacy(body)
    except _Fail as exc:
        return exc.response
