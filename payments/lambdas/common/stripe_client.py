import stripe


def get_stripe_client(secret_key):
    """stripe-python is configured via module-level state, but we still pass
    api_key explicitly on every call (below) so nothing depends on import order
    across warm Lambda invocations reusing a different secret."""
    stripe.api_key = secret_key
    return stripe


def get_or_create_customer(client, *, email, name, party_doctype, party_id, existing_customer_id=None):
    """Reuses existing_customer_id (the value already cached on the ERPNext
    party, if any) first. Falls back to a metadata search so a retry that lost
    track of the cached id still finds the same Customer instead of creating a
    duplicate — mirrors the Dwolla client's get-or-create-by-cached-id pattern."""
    if existing_customer_id:
        return existing_customer_id

    query = f"metadata['erpnext_party_doctype']:'{party_doctype}' AND metadata['erpnext_party_id']:'{party_id}'"
    found = client.Customer.search(query=query, limit=1)
    if found.data:
        return found.data[0].id

    customer = client.Customer.create(
        email=email,
        name=name,
        metadata={"erpnext_party_doctype": party_doctype, "erpnext_party_id": party_id},
    )
    return customer.id


def create_setup_intent(client, *, customer_id, payment_method_types=("card", "us_bank_account")):
    kwargs = {
        "customer": customer_id,
        "payment_method_types": list(payment_method_types),
        "usage": "off_session",
    }
    if "us_bank_account" in payment_method_types:
        kwargs["payment_method_options"] = {
            "us_bank_account": {
                "financial_connections": {"permissions": ["payment_method", "balances"]},
            },
        }
    return client.SetupIntent.create(**kwargs)


def retrieve_setup_intent(client, setup_intent_id):
    return client.SetupIntent.retrieve(setup_intent_id)


def retrieve_mandate(client, mandate_id):
    return client.Mandate.retrieve(mandate_id)


def create_payment_intent(client, *, customer_id, amount_cents, currency, payment_method_types,
                          metadata, idempotency_key, payment_method_id=None,
                          off_session=False, confirm=False):
    kwargs = {
        "customer": customer_id,
        "amount": int(amount_cents),
        "currency": currency,
        "payment_method_types": list(payment_method_types),
        "metadata": metadata,
    }
    if payment_method_id:
        kwargs["payment_method"] = payment_method_id
    if off_session:
        kwargs["off_session"] = True
    if confirm:
        kwargs["confirm"] = True
    return client.PaymentIntent.create(**kwargs, idempotency_key=idempotency_key)


def retrieve_payment_intent(client, payment_intent_id):
    return client.PaymentIntent.retrieve(payment_intent_id)


def construct_webhook_event(client, payload_bytes, sig_header, webhook_secret):
    return client.Webhook.construct_event(payload_bytes, sig_header, webhook_secret)
