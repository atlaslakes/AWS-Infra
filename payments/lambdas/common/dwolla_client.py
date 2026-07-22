import dwollav2


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
    resp = client.post(f"{customer_url}/funding-sources", {
        "plaidToken": processor_token,
        "name": name,
    })
    return resp.headers["Location"]  # Dwolla Funding Source resource URL


def create_transfer(client, *, source_url, destination_url, amount, currency="USD", metadata=None):
    body = {
        "_links": {
            "source": {"href": source_url},
            "destination": {"href": destination_url},
        },
        "amount": {"currency": currency, "value": f"{amount:.2f}"},
    }
    if metadata:
        body["metadata"] = metadata
    resp = client.post("transfers", body)
    return resp.headers["Location"]  # Dwolla Transfer resource URL


def get_transfer(client, transfer_url):
    return client.get(transfer_url).body
