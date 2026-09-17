import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.processor_token_create_request import ProcessorTokenCreateRequest
from plaid.model.webhook_verification_key_get_request import WebhookVerificationKeyGetRequest

_ENV_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def get_plaid_client(client_id, secret, environment="sandbox"):
    configuration = plaid.Configuration(
        host=_ENV_HOSTS[environment],
        api_key={"clientId": client_id, "secret": secret},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def create_link_token(client, *, user_id, client_name="Karavan Imports"):
    request = LinkTokenCreateRequest(
        products=[Products("auth")],
        client_name=client_name,
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
    )
    return client.link_token_create(request).to_dict()["link_token"]


def exchange_public_token(client, public_token):
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request).to_dict()
    return response["access_token"], response["item_id"]


def create_dwolla_processor_token(client, *, access_token, account_id):
    request = ProcessorTokenCreateRequest(
        access_token=access_token,
        account_id=account_id,
        processor="dwolla",
    )
    return client.processor_token_create(request).to_dict()["processor_token"]


def get_webhook_verification_key(client, key_id):
    request = WebhookVerificationKeyGetRequest(key_id=key_id)
    return client.webhook_verification_key_get(request).to_dict()["key"]
