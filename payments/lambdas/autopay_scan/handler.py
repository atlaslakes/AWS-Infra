import sys
import os
import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import stripe_config, erpnext_config
from common.stripe_client import get_stripe_client, create_payment_intent
from common.erpnext_client import ERPNextClient

import stripe as stripe_module

# (invoice doctype, party fieldname on invoice, party doctype, direction)
_INVOICE_TYPES = [
    # Customer owes us: charge the customer's saved payment method.
    ("Sales Invoice", "customer", "Customer", "collect"),
    # We owe the vendor: charge is on our side, not modeled via off-session
    # PaymentIntents here — payouts to vendors are handled outside Stripe's
    # customer-charge model, so "payout" invoices are skipped by this scan.
    ("Purchase Invoice", "supplier", "Supplier", "payout"),
]

# A brand-new invoice created over REST has this field as null, not "" — must
# include None or those invoices would never be picked up.
_DUE_STATUSES = (None, "", "Pending")


def handler(event, context):
    """Scheduled (EventBridge) — scans for due, auto-pay-enabled invoices and
    initiates the corresponding off-session Stripe PaymentIntent(s). Does NOT
    create a Payment Entry yet; that happens once stripe-webhook sees
    payment_intent.succeeded, since a charge can still fail/return after
    confirmation (especially ACH, which settles asynchronously).

    If an invoice has rows in custom_ach_installments, each row is a separate
    scheduled partial payment (installment plan). If it has no rows, the
    invoice is auto-paid in full on its due_date (the original, simpler
    behavior).
    """
    today = datetime.date.today().isoformat()

    stripe_cfg = stripe_config()
    client = get_stripe_client(stripe_cfg["secret_key"])

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])

    results = []
    skipped = []
    errors = []
    for invoice_doctype, party_field, party_doctype, direction in _INVOICE_TYPES:
        if direction != "collect":
            continue  # payouts are not modeled via Stripe customer charges

        due_invoices = erp.list(
            invoice_doctype,
            filters=[
                ["custom_autopay_enabled", "=", 1],
                ["status", "not in", ["Paid", "Cancelled", "Return", "Credit Note Issued"]],
            ],
            fields=["name"],
        )

        for row in due_invoices:
            try:
                _process_invoice(
                    erp, client, today,
                    invoice_doctype, party_field, party_doctype,
                    row["name"], results, skipped,
                )
            except Exception as exc:  # one bad invoice must not abort the whole scan
                errors.append({"invoice": row["name"], "error": str(exc)})

    out = {"processed": results, "skipped": skipped}
    if errors:
        out["errors"] = errors
        # Surface to the CloudWatch error alarm without losing the successes.
        raise RuntimeError(f"autopay-scan completed with {len(errors)} error(s): {errors}")
    return out


def _process_invoice(erp, client, today,
                     invoice_doctype, party_field, party_doctype,
                     invoice_name, results, skipped):
    inv = erp.get(invoice_doctype, invoice_name)
    party_id = inv[party_field]
    party = erp.get(party_doctype, party_id)
    customer_id = party.get("custom_stripe_customer_id") if party else None
    payment_method_id = party.get("custom_stripe_payment_method_id") if party else None
    if not customer_id or not payment_method_id:
        return  # no saved payment method yet — skip until it's linked

    method_type = party.get("custom_payment_method_type")
    if method_type == "Bank" and not party.get("custom_bank_linked"):
        return  # bank method not verified/active — skip

    # NACHA: never debit a customer's bank account without a retained
    # authorization on file. Cards don't require this.
    if method_type == "Bank" and not party.get("custom_ach_authorization_date"):
        skipped.append({"invoice": inv["name"], "reason": "no ACH authorization on file",
                        "party": party_id})
        return

    payment_method_types = ["us_bank_account"] if method_type == "Bank" else ["card"]
    currency = (inv.get("currency") or "usd").lower()
    installments = inv.get("custom_ach_installments") or []

    if installments:
        for installment in installments:
            if installment.get("stripe_payment_intent_id"):
                continue  # already initiated — never re-send
            if installment.get("status") not in _DUE_STATUSES:
                continue
            if (installment.get("scheduled_date") or "") > today:
                continue
            if float(installment.get("amount") or 0) <= 0:
                continue

            try:
                payment_intent = create_payment_intent(
                    client,
                    customer_id=customer_id,
                    amount_cents=round(float(installment["amount"]) * 100),
                    currency=currency,
                    payment_method_types=payment_method_types,
                    payment_method_id=payment_method_id,
                    off_session=True,
                    confirm=True,
                    metadata={
                        "invoice_doctype": invoice_doctype,
                        "invoice_name": inv["name"],
                        "installment_row": installment["name"],
                    },
                    idempotency_key=f"autopay:{invoice_doctype}:{inv['name']}:{installment['name']}",
                )
            except (stripe_module.error.CardError, stripe_module.error.InvalidRequestError) as exc:
                installment["status"] = "Failed"
                erp.update(invoice_doctype, inv["name"], {"custom_ach_installments": installments})
                skipped.append({"invoice": inv["name"], "installment": installment["name"], "reason": str(exc)})
                continue

            installment["status"] = "Processing"
            installment["stripe_payment_intent_id"] = payment_intent.id
            # Persist immediately after each transfer so a later crash in this
            # loop can't lose an already-initiated payment.
            erp.update(invoice_doctype, inv["name"], {"custom_ach_installments": installments})
            results.append({
                "invoice": inv["name"], "installment": installment["name"], "payment_intent": payment_intent.id,
            })
        return

    # Single full-amount auto-pay on due_date.
    if inv.get("custom_stripe_payment_intent_id"):
        return  # already initiated — never re-send
    if inv.get("custom_payment_status") not in _DUE_STATUSES:
        return
    if (inv.get("due_date") or "") > today:
        return
    amount = float(inv.get("outstanding_amount") or 0)
    if amount <= 0:
        return

    try:
        payment_intent = create_payment_intent(
            client,
            customer_id=customer_id,
            amount_cents=round(amount * 100),
            currency=currency,
            payment_method_types=payment_method_types,
            payment_method_id=payment_method_id,
            off_session=True,
            confirm=True,
            metadata={"invoice_doctype": invoice_doctype, "invoice_name": inv["name"]},
            idempotency_key=f"autopay:{invoice_doctype}:{inv['name']}:full:{inv.get('due_date')}",
        )
    except (stripe_module.error.CardError, stripe_module.error.InvalidRequestError) as exc:
        erp.update(invoice_doctype, inv["name"], {"custom_payment_status": "Failed"})
        skipped.append({"invoice": inv["name"], "reason": str(exc)})
        return

    erp.update(invoice_doctype, inv["name"], {
        "custom_stripe_payment_intent_id": payment_intent.id,
        "custom_payment_status": "Processing",
    })
    results.append({"invoice": inv["name"], "payment_intent": payment_intent.id})
