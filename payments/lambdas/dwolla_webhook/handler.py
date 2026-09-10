import base64
import datetime
import hashlib
import hmac
import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import dwolla_config, erpnext_config
from common.dwolla_client import get_dwolla_client, get_transfer, get_transfer_failure
from common.erpnext_client import ERPNextClient

# Dwolla ACH return codes that must never be auto-retried (unauthorized /
# disputed). They are flagged "Returned" rather than "Failed" so a human treats
# them differently — retry policy is a business decision, not decided here.
_UNAUTHORIZED_RETURN_CODES = {"R05", "R07", "R10", "R11", "R29", "R51"}

# Transfer webhook topics come in several prefixes depending on which leg / party
# Dwolla is reporting: transfer_*, bank_transfer_*, customer_transfer_*,
# customer_bank_transfer_*. Match on the suffix so every variant is covered.
_COMPLETED_SUFFIXES = ("transfer_completed",)
_FAILED_SUFFIXES = ("transfer_failed", "transfer_cancelled", "transfer_reclaimed")


def _ok(status):
    return {"statusCode": 200, "body": json.dumps({"status": status})}


def _raw_body(event):
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return body


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


def _create_payment_entry(erp, invoice_doctype, invoice_name, amount, transfer_id, ref_date):
    """Build the Payment Entry server-side (party, bank accounts, company and
    exchange rates all resolved by ERPNext from the invoice) then post it.

    Idempotent: if a Payment Entry already carries this transfer as its
    reference_no we assume the completion event was already processed.
    """
    if erp.exists("Payment Entry", [["reference_no", "=", transfer_id]]):
        return None

    pe = erp.call(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
        dt=invoice_doctype, dn=invoice_name, party_amount=amount,
    )
    if not pe:
        raise RuntimeError(f"get_payment_entry returned nothing for {invoice_doctype} {invoice_name}")

    pe["mode_of_payment"] = "ACH"
    pe["reference_no"] = transfer_id
    pe["reference_date"] = ref_date

    created = erp.create("Payment Entry", pe)
    erp.submit("Payment Entry", created["name"])
    return created["name"]


def handler(event, context):
    body_raw = _raw_body(event)
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    signature = headers.get("x-request-signature-sha256")

    dwolla_cfg = dwolla_config()
    if not _verify_signature(dwolla_cfg["webhook_secret"], body_raw, signature):
        return {"statusCode": 401, "body": json.dumps({"error": "invalid signature"})}

    payload = json.loads(body_raw)
    topic = (payload.get("topic") or "")
    transfer_url = payload.get("_links", {}).get("resource", {}).get("href")

    is_completed = topic.endswith(_COMPLETED_SUFFIXES)
    is_failed = topic.endswith(_FAILED_SUFFIXES)
    if not (is_completed or is_failed):
        return _ok(f"ignored topic {topic!r}")
    if not transfer_url:
        return _ok("ignored, no transfer link")

    dwolla_client = get_dwolla_client(dwolla_cfg["key"], dwolla_cfg["secret"], dwolla_cfg["environment"])
    transfer = get_transfer(dwolla_client, transfer_url)
    metadata = transfer.get("metadata") or {}
    invoice_doctype = metadata.get("invoice_doctype")
    invoice_name = metadata.get("invoice_name")
    installment_row = metadata.get("installment_row")
    transfer_id = transfer_url.rsplit("/", 1)[-1]

    if not invoice_doctype or not invoice_name:
        return _ok("no invoice metadata on transfer")

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])

    if is_completed:
        amount = float(transfer["amount"]["value"])
        ref_date = (transfer.get("created") or "")[:10] or datetime.date.today().isoformat()
        pe_name = _create_payment_entry(erp, invoice_doctype, invoice_name, amount, transfer_id, ref_date)

        if installment_row:
            _update_installment_row(erp, invoice_doctype, invoice_name, installment_row, {"status": "Completed"})
        else:
            erp.update(invoice_doctype, invoice_name, {"custom_ach_status": "Completed"})
        return _ok(f"reconciled{'' if pe_name else ' (already done)'}")

    # is_failed
    failure = get_transfer_failure(dwolla_client, transfer_url) or {}
    return_code = failure.get("code") or payload.get("returnCode")
    status = "Returned" if return_code in _UNAUTHORIZED_RETURN_CODES else "Failed"

    if installment_row:
        _update_installment_row(erp, invoice_doctype, invoice_name, installment_row,
                                {"status": status})
    else:
        erp.update(invoice_doctype, invoice_name, {"custom_ach_status": status})

    _cancel_payment_entries_for_transfer(erp, transfer_id)
    # A CloudWatch alarm on this Lambda's logged failures notifies a human —
    # deciding whether/how to retry an ACH return is a business decision.
    return _ok(f"marked {status} (return code {return_code or 'n/a'})")
