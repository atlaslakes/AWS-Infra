import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.auth import check_caller
from common.config import plaid_config
from common.plaid_client import get_plaid_client, create_link_token


def handler(event, context):
    """POST /link-token
    Body: {"party_id": "<ERPNext Customer or Supplier name>"}
    Called by Base44 right before launching Plaid Link for a user who wants
    to link a bank account for ACH auto-pay.
    """
    deny = check_caller(event)
    if deny:
        return deny

    body = json.loads(event.get("body") or "{}")
    party_id = body.get("party_id")
    if not party_id:
        return {"statusCode": 400, "body": json.dumps({"error": "party_id is required"})}

    cfg = plaid_config()
    client = get_plaid_client(cfg["client_id"], cfg["secret"], cfg["environment"])
    link_token = create_link_token(client, user_id=party_id)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"link_token": link_token}),
    }
