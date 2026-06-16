"""
Create a customer-facing landing workspace in ERPNext.

What this sets up:
1) Workspace: Customer Self-Service
2) Shortcuts:
   - Place Order (new Sales Order)
   - Track My Orders (Sales Order list)
   - Track Deliveries (Delivery Note list)
   - My Invoices (Sales Invoice list)
3) Optional: assign this workspace as default landing page for specific users

Usage:
  python scripts/setup_customer_landing_page.py

Optional env vars:
  ERPNEXT_URL
  ERPNEXT_API_KEY
  ERPNEXT_API_SECRET
  CUSTOMER_USERS   Comma-separated user IDs/emails to set default_workspace
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests


ERPNEXT_URL = os.getenv("ERPNEXT_URL", "http://3.216.86.193").strip().rstrip("/")
ERPNEXT_API_KEY = os.getenv("ERPNEXT_API_KEY", "647f56b706a1bea")
ERPNEXT_API_SECRET = os.getenv("ERPNEXT_API_SECRET", "6c615d3ea8cbd4d")
WORKSPACE_NAME = "Customer Self-Service"


class ERPClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {api_key}:{api_secret}",
                "Content-Type": "application/json",
            }
        )
        self.session.verify = False

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def ping(self) -> None:
        response = self.session.get(self._url("/api/method/ping"), timeout=20)
        response.raise_for_status()
        if response.json().get("message") != "pong":
            raise RuntimeError(f"Unexpected ping response: {response.text[:200]}")

    def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        response = self.session.get(
            self._url(f"/api/resource/{doctype}/{requests.utils.quote(name)}"),
            timeout=30,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("data")

    def insert_doc(self, doctype: str, doc: dict[str, Any]) -> dict[str, Any]:
        payload = dict(doc)
        payload.setdefault("doctype", doctype)
        response = self.session.post(
            self._url(f"/api/resource/{doctype}"),
            data=json.dumps(payload),
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"{doctype} insert failed {response.status_code}: {response.text[:1200]}")
        return response.json().get("data", {})

    def update_doc(self, doctype: str, name: str, doc: dict[str, Any]) -> dict[str, Any]:
        response = self.session.put(
            self._url(f"/api/resource/{doctype}/{requests.utils.quote(name)}"),
            data=json.dumps(doc),
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"{doctype} update failed {response.status_code}: {response.text[:1200]}")
        return response.json().get("data", {})


def workspace_payload() -> dict[str, Any]:
    shortcuts = [
        {
            "label": "Portal Home",
            "type": "URL",
            "url": "/me",
            "color": "blue",
        },
        {
            "label": "Place Order",
            "type": "DocType",
            "link_to": "Sales Order",
            "doc_view": "New",
            "color": "blue",
        },
        {
            "label": "Track My Orders",
            "type": "DocType",
            "link_to": "Sales Order",
            "doc_view": "List",
            "color": "green",
        },
        {
            "label": "Track Deliveries",
            "type": "DocType",
            "link_to": "Delivery Note",
            "doc_view": "List",
            "color": "orange",
        },
        {
            "label": "My Invoices",
            "type": "DocType",
            "link_to": "Sales Invoice",
            "doc_view": "List",
            "color": "purple",
        },
        {
            "label": "Portal Orders",
            "type": "URL",
            "url": "/orders",
            "color": "green",
        },
        {
            "label": "Portal Invoices",
            "type": "URL",
            "url": "/invoices",
            "color": "purple",
        },
    ]

    return {
        "name": WORKSPACE_NAME,
        "title": WORKSPACE_NAME,
        "label": WORKSPACE_NAME,
        "module": "Selling",
        "public": 1,
        "is_hidden": 0,
        "icon": "users",
        "indicator_color": "blue",
        "content": json.dumps(
            [
                {
                    "id": "header_customer_self_service",
                    "type": "header",
                    "data": {"text": "Customer Self-Service"},
                },
                {
                    "id": "para_customer_self_service",
                    "type": "paragraph",
                    "data": {
                        "text": "Use Desk shortcuts to place orders, and portal links to track orders and invoices."
                    },
                },
                {"id": "shortcut_portal_home", "type": "shortcut", "data": {"shortcut_name": "Portal Home"}},
                {"id": "shortcut_block", "type": "shortcut", "data": {"shortcut_name": "Place Order"}},
                {"id": "shortcut_block2", "type": "shortcut", "data": {"shortcut_name": "Track My Orders"}},
                {"id": "shortcut_block3", "type": "shortcut", "data": {"shortcut_name": "Track Deliveries"}},
                {"id": "shortcut_block4", "type": "shortcut", "data": {"shortcut_name": "My Invoices"}},
                {"id": "shortcut_portal_orders", "type": "shortcut", "data": {"shortcut_name": "Portal Orders"}},
                {"id": "shortcut_portal_invoices", "type": "shortcut", "data": {"shortcut_name": "Portal Invoices"}},
            ]
        ),
        "shortcuts": shortcuts,
        "roles": [{"role": "Customer"}],
    }


def ensure_workspace(client: ERPClient) -> str:
    payload = workspace_payload()
    existing = client.get_doc("Workspace", WORKSPACE_NAME)

    if existing is None:
        try:
            client.insert_doc("Workspace", payload)
            return "created"
        except Exception:
            # Fallback for ERPNext builds where child-table payloads are strict.
            minimal = {k: v for k, v in payload.items() if k not in {"roles", "shortcuts"}}
            client.insert_doc("Workspace", minimal)
            client.update_doc("Workspace", WORKSPACE_NAME, {"shortcuts": payload["shortcuts"]})
            return "created"

    update_payload = {
        "label": payload["label"],
        "module": payload["module"],
        "public": payload["public"],
        "is_hidden": payload["is_hidden"],
        "icon": payload["icon"],
        "indicator_color": payload["indicator_color"],
        "content": payload["content"],
        "shortcuts": payload["shortcuts"],
        "roles": payload["roles"],
    }

    try:
        client.update_doc("Workspace", WORKSPACE_NAME, update_payload)
    except Exception:
        client.update_doc(
            "Workspace",
            WORKSPACE_NAME,
            {k: v for k, v in update_payload.items() if k not in {"roles", "shortcuts"}},
        )
    return "updated"


def set_default_workspace(client: ERPClient, user_id: str, workspace_name: str) -> None:
    client.update_doc("User", user_id, {"default_workspace": workspace_name})


def main() -> None:
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    client = ERPClient(ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET)
    print(f"Connecting to {ERPNEXT_URL} ...")
    client.ping()
    print("Connected.")

    result = ensure_workspace(client)
    print(f"Workspace '{WORKSPACE_NAME}': {result}")

    raw_users = os.getenv("CUSTOMER_USERS", "").strip()
    if raw_users:
        users = [x.strip() for x in raw_users.split(",") if x.strip()]
        for user in users:
            try:
                set_default_workspace(client, user, WORKSPACE_NAME)
                print(f"Default workspace set for {user}")
            except Exception as exc:
                print(f"Could not set default workspace for {user}: {exc}")

    print("Done.")


if __name__ == "__main__":
    main()
