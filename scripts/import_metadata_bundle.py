"""
Import ERPNext metadata-only bundle into a target environment.

Usage:
  python scripts/import_metadata_bundle.py artifacts/metadata/metadata-bundle-<timestamp>.json

Optional env vars:
  ERPNEXT_URL
  ERPNEXT_API_KEY
  ERPNEXT_API_SECRET
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

ERPNEXT_URL = os.getenv("ERPNEXT_URL", "http://atlaslakeserp").strip().rstrip("/")
ERPNEXT_API_KEY = os.getenv("ERPNEXT_API_KEY", "")
ERPNEXT_API_SECRET = os.getenv("ERPNEXT_API_SECRET", "")

IMPORT_ORDER = [
    "Role",
    "Role Profile",
    "Module Profile",
    "Custom Field",
    "Property Setter",
    "Workspace",
    "Print Format",
    "Notification",
    "Client Script",
    "Server Script",
]

DROP_FIELDS = {
    "doctype",
    "creation",
    "modified",
    "modified_by",
    "owner",
    "docstatus",
    "idx",
    "_user_tags",
    "_comments",
    "_assign",
    "_liked_by",
}


class ERPClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        if not api_key or not api_secret:
            raise ValueError("ERPNEXT_API_KEY and ERPNEXT_API_SECRET are required")
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
        r = self.session.get(self._url("/api/method/ping"), timeout=20)
        r.raise_for_status()
        if r.json().get("message") != "pong":
            raise RuntimeError(f"Unexpected ping response: {r.text[:200]}")

    def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        r = self.session.get(
            self._url(f"/api/resource/{doctype}/{requests.utils.quote(name)}"),
            timeout=60,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("data")

    def insert_doc(self, doctype: str, payload: dict[str, Any]) -> None:
        doc = {"doctype": doctype, **payload}
        r = self.session.post(self._url(f"/api/resource/{doctype}"), data=json.dumps(doc), timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"insert failed {doctype}/{payload.get('name')}: {r.status_code} {r.text[:800]}")

    def update_doc(self, doctype: str, name: str, payload: dict[str, Any]) -> None:
        r = self.session.put(
            self._url(f"/api/resource/{doctype}/{requests.utils.quote(name)}"),
            data=json.dumps(payload),
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"update failed {doctype}/{name}: {r.status_code} {r.text[:800]}")


def sanitize_for_write(doc: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in doc.items():
        if key in DROP_FIELDS:
            continue
        result[key] = value
    return result


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/import_metadata_bundle.py <bundle.json>")

    path = Path(sys.argv[1]).resolve()
    if not path.exists():
        raise SystemExit(f"Bundle not found: {path}")

    bundle = json.loads(path.read_text(encoding="utf-8"))
    docs_by_type: dict[str, list[dict[str, Any]]] = bundle.get("doctypes", {})

    client = ERPClient(ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET)
    client.ping()

    for doctype in IMPORT_ORDER:
        docs = docs_by_type.get(doctype, [])
        if not docs:
            continue

        created = 0
        updated = 0
        failed = 0
        print(f"Importing {doctype} ({len(docs)}) ...")

        for raw in docs:
            name = raw.get("name")
            if not name:
                failed += 1
                continue

            payload = sanitize_for_write(raw)

            try:
                existing = client.get_doc(doctype, name)
                if existing is None:
                    client.insert_doc(doctype, payload)
                    created += 1
                else:
                    client.update_doc(doctype, name, payload)
                    updated += 1
            except Exception as exc:
                failed += 1
                print(f"- Failed {doctype}/{name}: {exc}")

        print(f"- {doctype}: created={created} updated={updated} failed={failed}")


if __name__ == "__main__":
    main()
