import base64
import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import stripe_config, erpnext_config
from common.stripe_client import get_stripe_client, construct_webhook_event
from common.erpnext_client import ERPNextClient

# Stripe error/decline codes on a failed us_bank_account PaymentIntent that
# indicate an unauthorized/disputed debit (never auto-retry these — a human
# must decide, same as the old Dwolla R05/R07/R10/R11/R29/R51 return codes).
_UNAUTHORIZED_CODES = {"debit_not_authorized", "payment_method_bank_account_blocked", "bank_account_unusable"}


def _ok(status):
    return {"statusCode": 200, "body": json.dumps({"status": status})}


def _raw_body(event):
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _update_installment_row(erp, invoice_doctype, invoice_name, row_name, updates):
    inv = erp.get(invoice_doctype, invoice_name)
    installments = inv.get("custom_ach_installments") or []
    changed = False
    for row in installments:
        if row["name"] == row_name:
            row.update(updates)
            changed = True
            break
    if changed:
        erp.update(invoice_doctype, invoice_name, {"custom_ach_installments": installments})
    return changed


def _cancel_payment_entries_for(erp, payment_intent_id):
    existing = erp.list(
        "Payment Entry",
        filters=[["reference_no", "=", payment_intent_id]],
        fields=["name", "docstatus"],
    )
    for pe in existing:
        if pe["docstatus"] == 1:
            erp.cancel("Payment Entry", pe["name"])


def _create_payment_entry(erp, invoice_doctype, invoice_name, amount, payment_intent_id, ref_date, mode_of_payment):
    """Idempotent: if a Payment Entry already carries this PaymentIntent id as
    its reference_no, the completion event was already processed."""
    if erp.exists("Payment Entry", [["reference_no", "=", payment_intent_id]]):
        return None

    # Deliberately NOT passing party_amount here: ERPNext's get_payment_entry
    # receives it as a raw querystring value and, in the version this site
    # runs, calls abs() on it without casting to a number first — crashes with
    # "TypeError: bad operand type for abs(): 'str'" every time. Omitting it
    # makes ERPNext default to the invoice's full outstanding amount instead;
    # for a partial (installment) payment we then override the amount fields
    # ourselves below.
    pe = erp.call(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
        dt=invoice_doctype, dn=invoice_name,
    )
    if not pe:
        raise RuntimeError(f"get_payment_entry returned nothing for {invoice_doctype} {invoice_name}")

    if abs(amount - float(pe.get("paid_amount") or 0)) > 0.01:
        pe["paid_amount"] = amount
        pe["received_amount"] = amount
        pe["base_paid_amount"] = amount
        pe["base_received_amount"] = amount
        pe["unallocated_amount"] = 0.0
        for ref in pe.get("references") or []:
            if ref.get("reference_doctype") == invoice_doctype and ref.get("reference_name") == invoice_name:
                ref["allocated_amount"] = amount

    pe["mode_of_payment"] = mode_of_payment
    pe["reference_no"] = payment_intent_id
    pe["reference_date"] = ref_date

    created = erp.create("Payment Entry", pe)
    erp.submit("Payment Entry", created["name"])
    return created["name"]


def _mode_of_payment(client, payment_intent):
    """payment_intent["payment_method_types"] lists every type the PaymentIntent
    was WILLING to accept, not which one was actually used — always retrieve the
    actual PaymentMethod to find that out."""
    payment_method_id = payment_intent.get("payment_method")
    if not payment_method_id:
        return "ACH" if "us_bank_account" in (payment_intent.get("payment_method_types") or []) else "Card"
    payment_method = client.PaymentMethod.retrieve(payment_method_id)
    return "ACH" if payment_method.type == "us_bank_account" else "Card"


def _handle_payment_succeeded(client, erp, payment_intent):
    metadata = payment_intent.get("metadata") or {}
    invoice_doctype = metadata.get("invoice_doctype")
    invoice_name = metadata.get("invoice_name")
    installment_row = metadata.get("installment_row")
    if not invoice_doctype or not invoice_name:
        return _ok("no invoice metadata on payment_intent")

    import datetime

    amount = payment_intent["amount"] / 100.0
    created_ts = payment_intent.get("created")
    ref_date = (
        datetime.datetime.utcfromtimestamp(created_ts).date().isoformat()
        if created_ts else datetime.date.today().isoformat()
    )
    mode_of_payment = _mode_of_payment(client, payment_intent)

    pe_name = _create_payment_entry(
        erp, invoice_doctype, invoice_name, amount, payment_intent["id"], ref_date, mode_of_payment,
    )

    if installment_row:
        _update_installment_row(erp, invoice_doctype, invoice_name, installment_row, {"status": "Completed"})
    else:
        erp.update(invoice_doctype, invoice_name, {"custom_payment_status": "Completed"})
    return _ok(f"reconciled{'' if pe_name else ' (already done)'}")


def _handle_payment_failed(erp, payment_intent):
    metadata = payment_intent.get("metadata") or {}
    invoice_doctype = metadata.get("invoice_doctype")
    invoice_name = metadata.get("invoice_name")
    installment_row = metadata.get("installment_row")
    if not invoice_doctype or not invoice_name:
        return _ok("no invoice metadata on payment_intent")

    last_error = payment_intent.get("last_payment_error") or {}
    code = last_error.get("code") or last_error.get("decline_code")
    status = "Returned" if code in _UNAUTHORIZED_CODES else "Failed"

    if installment_row:
        _update_installment_row(erp, invoice_doctype, invoice_name, installment_row, {"status": status})
    else:
        erp.update(invoice_doctype, invoice_name, {"custom_payment_status": status})

    _cancel_payment_entries_for(erp, payment_intent["id"])
    # A CloudWatch alarm on this Lambda's logged failures notifies a human —
    # deciding whether/how to retry a failed/returned payment is a business decision.
    return _ok(f"marked {status} (code {code or 'n/a'})")


def _handle_mandate_updated(erp, mandate):
    if mandate.get("status") == "active":
        return _ok("mandate active, no action")
    mandate_id = mandate.get("id")
    for doctype in ("Customer", "Supplier"):
        matches = erp.list(doctype, filters=[["custom_stripe_mandate_id", "=", mandate_id]], fields=["name"])
        if matches:
            erp.update(doctype, matches[0]["name"], {"custom_bank_linked": 0})
            return _ok(f"flagged stale bank link on {doctype} {matches[0]['name']}")
    return _ok("no party found for mandate")


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("stripe-signature")
    body_raw = _raw_body(event)

    stripe_cfg = stripe_config()
    client = get_stripe_client(stripe_cfg["secret_key"])
    try:
        webhook_event = construct_webhook_event(client, body_raw, sig_header, stripe_cfg["webhook_secret"])
    except Exception:
        return {"statusCode": 401, "body": json.dumps({"error": "invalid signature"})}

    event_type = webhook_event["type"]
    # stripe-python's StripeObject doesn't support dict methods like .get() —
    # convert to a plain (recursively-converted) dict so the handlers below
    # can use ordinary dict access throughout.
    data_object = webhook_event["data"]["object"].to_dict()

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])

    if event_type == "payment_intent.succeeded":
        return _handle_payment_succeeded(client, erp, data_object)
    if event_type == "payment_intent.payment_failed":
        return _handle_payment_failed(erp, data_object)
    if event_type == "mandate.updated":
        return _handle_mandate_updated(erp, data_object)
    if event_type in ("setup_intent.succeeded", "payment_method.automatically_updated"):
        return _ok(f"no-op for {event_type}")
    if event_type == "charge.dispute.created":
        # Out of scope for now — logged and acknowledged so Stripe doesn't retry;
        # a human follows up from the Stripe dashboard.
        return _ok("dispute logged")

    return _ok(f"ignored event type {event_type!r}")
