"""Auth for the Tap to Pay mobile app (drivers / sales reps).

The app logs each person into ERPNext with their OWN account
(POST /api/method/login) and forwards the resulting session id as the
`X-Frappe-Sid` header. We validate it against ERPNext on every call, so:
  * no shared secret is ever shipped inside the app binary,
  * disabling the ERPNext user (or logging them out) revokes access,
  * every PaymentIntent records who collected it.
"""

import json
import os

import requests

_ALLOWED_DEFAULT = "Accounts User,Sales User"


def _deny(status, message):
    return None, {"statusCode": status, "headers": {"Content-Type": "application/json"},
                  "body": json.dumps({"error": message})}


def allowed_roles():
    raw = os.environ.get("TERMINAL_ALLOWED_ROLES", _ALLOWED_DEFAULT)
    return {r.strip() for r in raw.split(",") if r.strip()}


def staff_user(event, erpnext_url):
    """Returns (user, None) when the caller is a logged-in ERPNext user holding
    one of TERMINAL_ALLOWED_ROLES, else (None, <401/403 response>)."""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sid = (headers.get("x-frappe-sid") or "").strip()
    if not sid or sid == "Guest":
        return _deny(401, "login required")

    base = erpnext_url.rstrip("/")
    cookies = {"sid": sid}
    r = requests.get(f"{base}/api/method/frappe.auth.get_logged_user", cookies=cookies, timeout=10)
    if r.status_code != 200:
        return _deny(401, "session expired")
    user = r.json().get("message")
    if not user or user == "Guest":
        return _deny(401, "session expired")

    r = requests.get(f"{base}/api/method/frappe.core.doctype.user.user.get_roles", cookies=cookies, timeout=10)
    if r.status_code != 200:
        return _deny(403, "could not verify roles")
    roles = set(r.json().get("message") or [])
    if not roles & allowed_roles():
        return _deny(403, "your ERPNext user is not allowed to take payments")
    return user, None
