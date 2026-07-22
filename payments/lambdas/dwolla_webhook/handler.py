import hashlib
import hmac
import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import dwolla_config, erpnext_config
from common.dwolla_client import get_dwolla_client, get_transfer
from common.erpnext_client import ERPNextClient

# Dwolla return codes that must never be auto-retried (unauthorized/disputed) —
# these get flagged Returned same as any other failure; retry policy is a
# business decision, not something this handler decides.
_UNAUTHORIZED_RETURN_CODES = {"R10", "R11", "R29"}


def _verify_signature(secret, body_raw, signature):
    expected = hmac.new(secret.encode(), body_raw.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


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


def _cancel_payment_entries_for_transfer(erp, transfer_id):
    existing = erp.list(
        "Payment Entry",
        filters=[["reference_no", "=", transfer_id]],
        fields=["name", "docstatus"],
    )
    for pe in existing:
        if pe["docstatus"] == 1:
            erp.cancel("Payment Entry", pe["name"])


def handler(event, context):
    body_raw = event.get("body") or "{}"
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    signature = headers.get("x-request-signature-sha256")

    dwolla_cfg = dwolla_config()
    if not _verify_signature(dwolla_cfg["webhook_secret"], body_raw, signature):
        return {"statusCode": 401, "body": json.dumps({"error": "invalid signature"})}

    payload = json.loads(body_raw)
    topic = payload.get("topic", "")
    transfer_url = payload.get("_links", {}).get("resource", {}).get("href")
    if not transfer_url:
        return {"statusCode": 200, "body": json.dumps({"status": "ignored, no transfer link"})}

    dwolla_client = get_dwolla_client(dwolla_cfg["key"], dwolla_cfg["secret"], dwolla_cfg["environment"])
    transfer = get_transfer(dwolla_client, transfer_url)
    metadata = transfer.get("metadata") or {}
    invoice_doctype = metadata.get("invoice_doctype")
    invoice_name = metadata.get("invoice_name")
    installment_row = metadata.get("installment_row")
    transfer_id = transfer_url.rsplit("/", 1)[-1]

    if not invoice_doctype or not invoice_name:
        return {"statusCode": 200, "body": json.dumps({"status": "no invoice metadata on transfer"})}

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])

    if topic == "transfer_completed":
        amount = transfer["amount"]["value"]
        payment_entry = erp.create("Payment Entry", {
            "doctype": "Payment Entry",
            "payment_type": "Receive" if invoice_doctype == "Sales Invoice" else "Pay",
            "reference_no": transfer_id,
            "reference_date": None,
            "mode_of_payment": "ACH",
            "references": [{
                "doctype": "Payment Entry Reference",
                "reference_doctype": invoice_doctype,
                "reference_name": invoice_name,
                "allocated_amount": amount,
            }],
        })
        erp.submit("Payment Entry", payment_entry["name"])

        if installment_row:
            _update_installment_row(erp, invoice_doctype, invoice_name, installment_row, {"status": "Completed"})
        else:
            erp.update(invoice_doctype, invoice_name, {"custom_ach_status": "Completed"})

    elif topic in ("transfer_failed", "transfer_cancelled", "customer_bank_transfer_failed"):
        return_code = payload.get("returnCode") or payload.get("code")
        status = "Failed" if return_code not in _UNAUTHORIZED_RETURN_CODES else "Returned"

        if installment_row:
            _update_installment_row(erp, invoice_doctype, invoice_name, installment_row, {"status": status})
        else:
            erp.update(invoice_doctype, invoice_name, {"custom_ach_status": status})

        _cancel_payment_entries_for_transfer(erp, transfer_id)
        # CloudWatch alarm on this Lambda's error/logged-failure metric notifies
        # a human for follow-up — retrying a return is a business decision,
        # not automated here.

    return {"statusCode": 200, "body": json.dumps({"status": "ok"})}
