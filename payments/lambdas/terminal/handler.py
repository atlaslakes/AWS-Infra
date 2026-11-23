import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import stripe_config, erpnext_config
from common.staff_auth import staff_user
from common.stripe_client import get_stripe_client, create_payment_intent, blocking_payment_intent
from common.erpnext_client import ERPNextClient
from common import surcharge

_CHANNEL = "tap_to_pay"


def _resp(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def _location_id(client):
    """TERMINAL_LOCATION_ID if set, else the account's first Terminal Location
    (create one once in Stripe Dashboard -> Terminal -> Locations)."""
    configured = os.environ.get("TERMINAL_LOCATION_ID", "").strip()
    if configured:
        return configured
    found = client.terminal.Location.list(limit=1)
    return found.data[0].id if found.data else None


def _connection_token(client, user, body):
    """POST /terminal/connection-token — the Stripe Terminal SDK's token
    provider calls this whenever it needs to (re)connect."""
    location = _location_id(client)
    if not location:
        return _resp(500, {"error": "no Stripe Terminal Location configured"})
    token = client.terminal.ConnectionToken.create(location=location)
    return _resp(200, {"secret": token.secret, "location_id": location})


def _payment_intent(client, erp, user, body):
    """POST /terminal/payment-intent  Body: {invoice_name}
    Creates a card_present PaymentIntent for the invoice's outstanding amount
    (no surcharge yet — we don't know the card until it's tapped)."""
    invoice_name = body.get("invoice_name")
    if not invoice_name:
        return _resp(400, {"error": "invoice_name is required"})
    invoice = erp.get("Sales Invoice", invoice_name)
    if invoice is None:
        return _resp(404, {"error": f"Sales Invoice {invoice_name} not found"})
    if int(invoice.get("docstatus") or 0) != 1:
        return _resp(400, {"error": "invoice is not submitted"})
    base_cents = round(float(invoice.get("outstanding_amount") or 0) * 100)
    if base_cents <= 0:
        return _resp(400, {"error": "invoice has no outstanding amount"})

    blocking = blocking_payment_intent(client, erp, "Sales Invoice", invoice_name)
    if blocking:
        return _resp(409, {"error": "a payment for this invoice is already in progress", "payment_intent_id": blocking})

    customer = erp.get("Customer", invoice["customer"]) or {}
    currency = (invoice.get("currency") or "usd").lower()
    pi = create_payment_intent(
        client,
        customer_id=customer.get("custom_stripe_customer_id"),
        amount_cents=base_cents,
        currency=currency,
        payment_method_types=["card_present"],
        description=f"Karavan Imports invoice {invoice_name}",
        metadata={
            "invoice_doctype": "Sales Invoice",
            "invoice_name": invoice_name,
            "channel": _CHANNEL,
            "collected_by": user,
            "base_cents": str(base_cents),
            "surcharge_cents": "0",
        },
    )
    return _resp(200, {
        "payment_intent_id": pi.id,
        "client_secret": pi.client_secret,
        "base_cents": base_cents,
        "currency": currency,
        "customer_name": invoice.get("customer_name") or invoice["customer"],
    })


def _apply_surcharge(client, erp, user, body):
    """POST /terminal/apply-surcharge  Body: {payment_intent_id}
    Called after the app's collectPaymentMethod (with updatePaymentIntent:
    true) and BEFORE confirmPaymentIntent. Reads the tapped card's funding
    type and, for credit cards, raises the PaymentIntent amount by the
    surcharge. The app must show the returned breakdown to the customer and
    get their OK before confirming. Idempotent: always recomputed from the
    base amount stored at creation."""
    pi_id = body.get("payment_intent_id")
    if not pi_id:
        return _resp(400, {"error": "payment_intent_id is required"})

    # StripeObject isn't a dict (no .get) — work on a plain recursive copy.
    pi = client.PaymentIntent.retrieve(pi_id, expand=["payment_method"]).to_dict()
    metadata = dict(pi.get("metadata") or {})
    if metadata.get("channel") != _CHANNEL:
        return _resp(400, {"error": "not a Tap to Pay payment"})
    if pi["status"] != "requires_confirmation":
        return _resp(409, {"error": f"payment is {pi['status']}, expected requires_confirmation"})
    pm = pi.get("payment_method")
    if not isinstance(pm, dict) or pm.get("type") not in ("card_present", "interac_present"):
        return _resp(409, {"error": "no tapped card on this payment yet"})
    card = pm.get(pm["type"]) or {}

    invoice_name = metadata["invoice_name"]
    base_cents = int(metadata["base_cents"])
    invoice = erp.get("Sales Invoice", invoice_name)
    if invoice is None or round(float(invoice.get("outstanding_amount") or 0) * 100) != base_cents:
        # Paid/credited elsewhere since the tap started — don't charge a stale amount.
        client.PaymentIntent.cancel(pi_id)
        return _resp(409, {"error": "invoice balance changed; start the payment again"})

    breakdown = surcharge.compute(
        base_cents,
        funding=card.get("funding"),
        invoice_doctype="Sales Invoice",
        billing_state=surcharge.billing_state_for(erp, invoice),
    )
    metadata.update({
        "surcharge_cents": str(breakdown["surcharge_cents"]),
        "surcharge_rate": breakdown["surcharge_rate"],
        "card_funding": breakdown["funding"] or "",
    })
    client.PaymentIntent.modify(
        pi_id,
        amount=breakdown["total_cents"],
        description=surcharge.describe(invoice_name, breakdown),
        metadata=metadata,
    )
    breakdown.update({
        "payment_intent_id": pi_id,
        "currency": pi["currency"],
        "card_brand": card.get("brand"),
        "card_last4": card.get("last4"),
    })
    return _resp(200, breakdown)


_ROUTES = {
    "/terminal/connection-token": _connection_token,
    "/terminal/payment-intent": _payment_intent,
    "/terminal/apply-surcharge": _apply_surcharge,
}


def handler(event, context):
    erp_cfg = erpnext_config()
    user, deny = staff_user(event, erp_cfg["url"])
    if deny:
        return deny

    path = (event.get("rawPath") or event.get("routeKey") or "").rstrip("/")
    route = next((fn for suffix, fn in _ROUTES.items() if path.endswith(suffix)), None)
    if route is None:
        return _resp(404, {"error": "unknown route"})

    try:
        body = json.loads(event.get("body") or "{}")
    except ValueError:
        return _resp(400, {"error": "body must be JSON"})

    client = get_stripe_client(stripe_config()["secret_key"])
    if route is _connection_token:
        return route(client, user, body)
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])
    return route(client, erp, user, body)
