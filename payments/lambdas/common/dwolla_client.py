import uuid

import dwollav2

# Stable namespace for deriving deterministic Idempotency-Key values from a
# business key (e.g. an invoice + installment). Same business key -> same UUID ->
# Dwolla treats a retried POST /transfers as the original and does not create a
# second transfer.
_IDEMPOTENCY_NAMESPACE = uuid.UUID("6f2b9d94-1c3e-4d0a-9b7a-0e5c8a1f2d34")


def idempotency_key(business_key):
    """Deterministic 36-char key for a logical transfer. Pass something that
    uniquely identifies the payment attempt and never changes on retry."""
    return str(uuid.uuid5(_IDEMPOTENCY_NAMESPACE, str(business_key)))


def get_dwolla_client(key, secret, environment="sandbox"):
    """environment is 'sandbox' or 'production'."""
    app = dwollav2.Client(
        id=key,
        secret=secret,
        environment=environment,
    )
    return app.Auth.client()


def create_customer(client, *, first_name, last_name, email, customer_type="unverified"):
    resp = client.post("customers", {
        "firstName": first_name,
        "lastName": last_name,
        "email": email,
        "type": customer_type,
    })
    return resp.headers["Location"]  # Dwolla Customer resource URL, used as the "customer id"


def attach_funding_source_from_plaid(client, customer_url, *, processor_token, name):
    try:
        resp = client.post(f"{customer_url}/funding-sources", {
            "plaidToken": processor_token,
            "name": name,
        })
        return resp.headers["Location"]  # Dwolla Funding Source resource URL
    except Exception as exc:
        body = getattr(exc, "body", None)
        if isinstance(body, dict) and body.get("code") == "DuplicateResource":
            # This bank account is already attached to the customer — reuse it
            # instead of 500ing or orphaning a second funding source.
            existing = (body.get("_links") or {}).get("about", {}).get("href")
            if existing:
                return existing
        raise


def get_funding_source(client, funding_source_url):
    return client.get(funding_source_url).body


def create_transfer(client, *, source_url, destination_url, amount, currency="USD",
                    metadata=None, idem_key=None):
    """Initiate an ACH transfer.

    idem_key: an Idempotency-Key (see idempotency_key()). Strongly recommended —
    without it, any retry of this call creates a duplicate transfer / duplicate
    ACH debit. If the key was already used, Dwolla returns the original transfer.
    """
    body = {
        "_links": {
            "source": {"href": source_url},
            "destination": {"href": destination_url},
        },
        "amount": {"currency": currency, "value": f"{float(amount):.2f}"},
    }
    if metadata:
        body["metadata"] = metadata
    headers = {"Idempotency-Key": idem_key} if idem_key else None
    resp = client.post("transfers", body, headers)
    return resp.headers["Location"]  # Dwolla Transfer resource URL


def get_transfer(client, transfer_url):
    return client.get(transfer_url).body


def get_transfer_failure(client, transfer_url):
    """Returns the ACH return details for a failed transfer, or None.
    The failure code (R01, R10, ...) is NOT in the webhook payload — it lives
    on this sub-resource."""
    try:
        return client.get(f"{transfer_url}/failure").body
    except Exception:
        return None
