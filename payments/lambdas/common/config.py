import json
import os
import boto3

_secret_cache = None


def load_secrets():
    """Fetches the PaymentsSecret JSON blob once per Lambda execution
    environment (cached across warm invocations)."""
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache

    secret_arn = os.environ["PAYMENTS_SECRET_ARN"]
    client = boto3.client("secretsmanager")
    value = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    _secret_cache = json.loads(value)
    return _secret_cache


def erpnext_config():
    secrets = load_secrets()
    return {
        "url": os.environ.get("ERPNEXT_URL", "https://www.karavanimports.com"),
        "api_key": secrets["erpnext_api_key"],
        "api_secret": secrets["erpnext_api_secret"],
    }


def caller_shared_secret():
    """Shared secret the caller (Base44) must present on the client-facing
    endpoints. Absent/empty in the secret => caller auth is disabled (only
    acceptable in a throwaway sandbox)."""
    return load_secrets().get("base44_shared_secret") or ""


def dwolla_config():
    secrets = load_secrets()
    return {
        "key": secrets["dwolla_key"],
        "secret": secrets["dwolla_secret"],
        "environment": secrets["dwolla_environment"],
        "webhook_secret": secrets["dwolla_webhook_secret"],
        # Atlas Lakes' own Dwolla funding source (the business bank account):
        # source of outbound vendor payments, destination of inbound customer collections.
        "master_funding_source_url": secrets["dwolla_master_funding_source_url"],
    }


def plaid_config():
    secrets = load_secrets()
    return {
        "client_id": secrets["plaid_client_id"],
        "secret": secrets["plaid_secret"],
        "environment": secrets["plaid_env"],
    }
