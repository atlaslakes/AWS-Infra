import sys
import os
import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import dwolla_config, erpnext_config
from common.dwolla_client import get_dwolla_client, create_transfer
from common.erpnext_client import ERPNextClient

# (invoice doctype, party fieldname on invoice, party doctype, transfer direction)
_INVOICE_TYPES = [
    # Customer owes us: debit the customer's funding source, credit our master account.
    ("Sales Invoice", "customer", "Customer", "collect"),
    # We owe the vendor: debit our master account, credit the vendor's funding source.
    ("Purchase Invoice", "supplier", "Supplier", "payout"),
]

_DUE_STATUSES = ("", "Pending")


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
    for invoice_doctype, party_field, party_doctype, direction in _INVOICE_TYPES:
        due_invoices = erp.list(
            invoice_doctype,
            filters=[
                ["custom_autopay_enabled", "=", 1],
                ["status", "not in", ["Paid", "Cancelled"]],
            ],
            fields=["name"],
        )

        for row in due_invoices:
            inv = erp.get(invoice_doctype, row["name"])
            party_id = inv[party_field]
            party = erp.get(party_doctype, party_id)
            funding_source = party.get("custom_dwolla_funding_source_id") if party else None
            if not funding_source:
                continue  # no linked bank account yet — skip until it's linked

            source_url, destination_url = _funding_source_urls(direction, funding_source, master_url)
            installments = inv.get("custom_ach_installments") or []

            if installments:
                changed = False
                for installment in installments:
                    if installment.get("status") not in _DUE_STATUSES:
                        continue
                    if (installment.get("scheduled_date") or "") > today:
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
                    )
                    installment["status"] = "Processing"
                    installment["ach_transfer_id"] = transfer_url
                    changed = True
                    results.append({"invoice": inv["name"], "installment": installment["name"], "transfer": transfer_url})

                if changed:
                    erp.update(invoice_doctype, inv["name"], {"custom_ach_installments": installments})

            else:
                if (inv.get("due_date") or "") > today:
                    continue
                if inv.get("custom_ach_status") not in _DUE_STATUSES:
                    continue

                transfer_url = create_transfer(
                    dwolla_client,
                    source_url=source_url,
                    destination_url=destination_url,
                    amount=inv["outstanding_amount"],
                    metadata={"invoice_doctype": invoice_doctype, "invoice_name": inv["name"]},
                )

                erp.update(invoice_doctype, inv["name"], {
                    "custom_ach_transfer_id": transfer_url,
                    "custom_ach_status": "Processing",
                })
                results.append({"invoice": inv["name"], "transfer": transfer_url})

    return {"processed": results}
