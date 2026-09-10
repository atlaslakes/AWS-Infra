import sys
import os
import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import dwolla_config, erpnext_config
from common.dwolla_client import get_dwolla_client, create_transfer, idempotency_key
from common.erpnext_client import ERPNextClient

# (invoice doctype, party fieldname on invoice, party doctype, transfer direction)
_INVOICE_TYPES = [
    # Customer owes us: debit the customer's funding source, credit our master account.
    ("Sales Invoice", "customer", "Customer", "collect"),
    # We owe the vendor: debit our master account, credit the vendor's funding source.
    ("Purchase Invoice", "supplier", "Supplier", "payout"),
]

# A brand-new invoice created over REST has this field as null, not "" — must
# include None or those invoices would never be picked up.
_DUE_STATUSES = (None, "", "Pending")


def _funding_source_urls(direction, party_funding_source, master_url):
    if direction == "collect":
        return party_funding_source, master_url
    return master_url, party_funding_source


def handler(event, context):
    """Scheduled (EventBridge) — scans for due, auto-pay-enabled invoices and
    initiates the corresponding Dwolla ACH transfer(s). Does NOT create a
    Payment Entry yet; that happens once the dwolla_webhook handler sees
    transfer_completed, since ACH can still fail/return after initiation.

    If an invoice has rows in custom_ach_installments, each row is a
    separate scheduled partial payment (installment plan). If it has no
    rows, the invoice is auto-paid in full on its due_date (the original,
    simpler behavior).
    """
    today = datetime.date.today().isoformat()

    dwolla_cfg = dwolla_config()
    dwolla_client = get_dwolla_client(dwolla_cfg["key"], dwolla_cfg["secret"], dwolla_cfg["environment"])
    master_url = dwolla_cfg["master_funding_source_url"]

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])

    results = []
    skipped = []
    errors = []
    for invoice_doctype, party_field, party_doctype, direction in _INVOICE_TYPES:
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
                    erp, dwolla_client, master_url, today,
                    invoice_doctype, party_field, party_doctype, direction,
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


def _process_invoice(erp, dwolla_client, master_url, today,
                     invoice_doctype, party_field, party_doctype, direction,
                     invoice_name, results, skipped):
    inv = erp.get(invoice_doctype, invoice_name)
    party_id = inv[party_field]
    party = erp.get(party_doctype, party_id)
    funding_source = party.get("custom_dwolla_funding_source_id") if party else None
    if not funding_source or (party and not party.get("custom_bank_linked")):
        return  # no verified linked bank account yet — skip until it's linked

    # NACHA: never debit a customer without a retained authorization on file.
    if direction == "collect" and not party.get("custom_ach_authorization_date"):
        skipped.append({"invoice": inv["name"], "reason": "no ACH authorization on file",
                        "party": party_id})
        return

    source_url, destination_url = _funding_source_urls(direction, funding_source, master_url)
    installments = inv.get("custom_ach_installments") or []

    if installments:
        for installment in installments:
            if installment.get("ach_transfer_id"):
                continue  # already initiated — never re-send
            if installment.get("status") not in _DUE_STATUSES:
                continue
            if (installment.get("scheduled_date") or "") > today:
                continue
            if float(installment.get("amount") or 0) <= 0:
                continue

            transfer_url = create_transfer(
                dwolla_client,
                source_url=source_url,
                destination_url=destination_url,
                amount=installment["amount"],
                metadata={
                    "invoice_doctype": invoice_doctype,
                    "invoice_name": inv["name"],
                    "installment_row": installment["name"],
                },
                idem_key=idempotency_key(
                    f"{invoice_doctype}|{inv['name']}|inst|{installment['name']}"
                ),
            )
            installment["status"] = "Processing"
            installment["ach_transfer_id"] = transfer_url
            # Persist immediately after each transfer so a later crash in this
            # loop can't lose an already-initiated payment.
            erp.update(invoice_doctype, inv["name"], {"custom_ach_installments": installments})
            results.append({
                "invoice": inv["name"], "installment": installment["name"], "transfer": transfer_url,
            })
        return

    # Single full-amount auto-pay on due_date.
    if inv.get("custom_ach_transfer_id"):
        return  # already initiated — never re-send
    if inv.get("custom_ach_status") not in _DUE_STATUSES:
        return
    if (inv.get("due_date") or "") > today:
        return
    amount = float(inv.get("outstanding_amount") or 0)
    if amount <= 0:
        return

    transfer_url = create_transfer(
        dwolla_client,
        source_url=source_url,
        destination_url=destination_url,
        amount=amount,
        metadata={"invoice_doctype": invoice_doctype, "invoice_name": inv["name"]},
        idem_key=idempotency_key(
            f"{invoice_doctype}|{inv['name']}|due|{inv.get('due_date')}|{amount:.2f}"
        ),
    )
    erp.update(invoice_doctype, inv["name"], {
        "custom_ach_transfer_id": transfer_url,
        "custom_ach_status": "Processing",
    })
    results.append({"invoice": inv["name"], "transfer": transfer_url})
