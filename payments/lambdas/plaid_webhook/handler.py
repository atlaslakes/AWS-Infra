import base64
import hashlib
import hmac
import json
import sys
import os
import time

import jwt
from jwt import PyJWK

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.config import erpnext_config, plaid_config
from common.erpnext_client import ERPNextClient
from common.plaid_client import get_plaid_client, get_webhook_verification_key

_STALE_LINK_CODES = {"ITEM_LOGIN_REQUIRED", "PENDING_EXPIRATION"}

_MAX_IAT_AGE_SECONDS = 300

_jwk_cache = {}


def _verify_signature(plaid_client, body_raw, headers):
    token = headers.get("plaid-verification")
    if not token:
        return False

    try:
        kid = jwt.get_unverified_header(token)["kid"]

        if kid not in _jwk_cache:
            _jwk_cache[kid] = get_webhook_verification_key(plaid_client, kid)
        jwk = PyJWK.from_json(json.dumps(_jwk_cache[kid]))

        claims = jwt.decode(token, key=jwk.key, algorithms=["ES256"])

        if time.time() - claims["iat"] > _MAX_IAT_AGE_SECONDS:
            return False

        expected_hash = hashlib.sha256(body_raw.encode()).hexdigest()
        return hmac.compare_digest(expected_hash, claims.get("request_body_sha256") or "")
    except Exception:
        return False


def _find_party_by_plaid_item(erp, item_id):
    # item_id isn't stored directly; matched via the Dwolla customer/funding
    # source IDs recorded during exchange-and-attach, keyed off Plaid's
    # webhook payload which includes the item_id we cached at link time.
    for doctype in ("Customer", "Supplier"):
        matches = erp.list(doctype, filters=[["custom_plaid_item_id", "=", item_id]], fields=["name"])
        if matches:
            return doctype, matches[0]["name"]
    return None, None


def handler(event, context):
    body_raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body_raw = base64.b64decode(body_raw).decode("utf-8")
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    plaid_cfg = plaid_config()
    plaid_client = get_plaid_client(plaid_cfg["client_id"], plaid_cfg["secret"], plaid_cfg["environment"])
    if not _verify_signature(plaid_client, body_raw, headers):
        return {"statusCode": 401, "body": json.dumps({"error": "invalid signature"})}

    payload = json.loads(body_raw)
    webhook_code = payload.get("webhook_code")
    item_id = payload.get("item_id")

    if webhook_code not in _STALE_LINK_CODES or not item_id:
        return {"statusCode": 200, "body": json.dumps({"status": "ignored"})}

    erp_cfg = erpnext_config()
    erp = ERPNextClient(erp_cfg["url"], erp_cfg["api_key"], erp_cfg["api_secret"])

    doctype, party_id = _find_party_by_plaid_item(erp, item_id)
    if party_id:
        erp.update(doctype, party_id, {"custom_bank_linked": 0})

    return {"statusCode": 200, "body": json.dumps({"status": "ok"})}
