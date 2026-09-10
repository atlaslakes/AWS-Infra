import hmac
import json

from common.config import caller_shared_secret

_UNAUTHORIZED = {
    "statusCode": 401,
    "headers": {"Content-Type": "application/json"},
    "body": json.dumps({"error": "unauthorized"}),
}


def _presented_secret(event):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    # Accept either a dedicated header or a bearer token.
    if headers.get("x-api-key"):
        return headers["x-api-key"]
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return ""


def check_caller(event):
    """Guards the client-facing endpoints (/link-token, /exchange-and-attach),
    which are otherwise open to the internet. Returns a 401 response dict to
    return immediately, or None when the caller is authorised.

    The expected secret lives in PaymentsSecret.base44_shared_secret and is
    sent by Base44 as `X-Api-Key` (or `Authorization: Bearer <secret>`).
    """
    expected = caller_shared_secret()
    if not expected:
        # No secret configured: fail closed everywhere except an explicit
        # sandbox opt-out, so a missing secret can't silently expose prod.
        return None if _sandbox_optout() else _UNAUTHORIZED
    presented = _presented_secret(event)
    if presented and hmac.compare_digest(presented, expected):
        return None
    return _UNAUTHORIZED


def _sandbox_optout():
    import os
    return os.environ.get("ALLOW_UNAUTHENTICATED_CALLERS") == "true"
