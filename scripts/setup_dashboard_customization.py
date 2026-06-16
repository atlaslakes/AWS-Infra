"""
Apply ERPNext dashboard-related customizations directly via REST API.

What this configures:
1) Item uniqueness controls
   - Custom Field: Item.custom_sku (unique)
   - Custom Field: Item.custom_invoice_alias (unique)
2) Duplicate prevention script
   - Server Script: Item Before Save near-duplicate validator
3) Invoice send automation
   - Notification: Sales Invoice -> customer email on submit
4) Sales/finance reporting data sources
   - Query Reports used for dashboard tables/charts

Usage:
  python scripts/setup_dashboard_customization.py

Optional env vars:
  ERPNEXT_URL
  ERPNEXT_API_KEY
  ERPNEXT_API_SECRET
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests


ERPNEXT_URL = os.getenv("ERPNEXT_URL", "http://atlaslakeserp").strip().rstrip("/")
ERPNEXT_API_KEY = os.getenv("ERPNEXT_API_KEY", "647f56b706a1bea")
ERPNEXT_API_SECRET = os.getenv("ERPNEXT_API_SECRET", "6c615d3ea8cbd4d")

ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT_PATH = ROOT / "configuration" / "erpnext-item-uniqueness-server-script.py"
SQL_TEMPLATES_PATH = ROOT / "configuration" / "dashboard-report-queries.sql"


class ERPClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"token {api_key}:{api_secret}", "Content-Type": "application/json"}
        )
        self.session.verify = False

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def ping(self) -> None:
        r = self.session.get(self._url("/api/method/ping"), timeout=20)
        r.raise_for_status()
        msg = r.json().get("message")
        if msg != "pong":
            raise RuntimeError(f"Unexpected ping response: {r.text[:200]}")

    def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        r = self.session.get(self._url(f"/api/resource/{doctype}/{requests.utils.quote(name)}"), timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("data")

    def insert_doc(self, doctype: str, doc: dict[str, Any]) -> dict[str, Any]:
        payload = dict(doc)
        payload.setdefault("doctype", doctype)
        r = self.session.post(self._url(f"/api/resource/{doctype}"), data=json.dumps(payload), timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"{doctype} insert failed {r.status_code}: {r.text[:1200]}")
        return r.json().get("data", {})

    def update_doc(self, doctype: str, name: str, doc: dict[str, Any]) -> dict[str, Any]:
        r = self.session.put(
            self._url(f"/api/resource/{doctype}/{requests.utils.quote(name)}"),
            data=json.dumps(doc),
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"{doctype} update failed {r.status_code}: {r.text[:1200]}")
        return r.json().get("data", {})

    def upsert_doc(self, doctype: str, name: str, create_doc: dict[str, Any], update_doc: dict[str, Any] | None = None) -> str:
        existing = self.get_doc(doctype, name)
        if existing is None:
            self.insert_doc(doctype, create_doc)
            return "created"
        if update_doc:
            self.update_doc(doctype, name, update_doc)
            return "updated"
        return "exists"


def ensure_custom_fields(client: ERPClient) -> None:
    fields = [
        {
            "name": "Item-custom_sku",
            "doc": {
                "dt": "Item",
                "label": "SKU",
                "fieldname": "custom_sku",
                "fieldtype": "Data",
                "unique": 1,
                "insert_after": "item_name",
                "in_list_view": 1,
                "description": "Unique SKU for quick item lookup.",
            },
        },
        {
            "name": "Item-custom_invoice_alias",
            "doc": {
                "dt": "Item",
                "label": "Invoice Alias",
                "fieldname": "custom_invoice_alias",
                "fieldtype": "Data",
                "unique": 1,
                "insert_after": "custom_sku",
                "in_list_view": 1,
                "description": "Unique invoice/search alias to avoid similar item conflicts.",
            },
        },
    ]

    print("\n[Custom Fields]")
    for field in fields:
        name = field["name"]
        payload = {"name": name, **field["doc"]}
        result = client.upsert_doc("Custom Field", name, payload, field["doc"])
        print(f"- {name}: {result}")


def ensure_server_script(client: ERPClient) -> None:
    print("\n[Server Script]")
    script_name = "Item Uniqueness Guard"
    script_code = SERVER_SCRIPT_PATH.read_text(encoding="utf-8")
    # Remove script heading comments; keep executable body only.
    script_body_lines = [ln for ln in script_code.splitlines() if not ln.startswith("# ")]
    script_body = "\n".join(script_body_lines).strip() + "\n"

    create_doc = {
        "name": script_name,
        "script_type": "DocType Event",
        "reference_doctype": "Item",
        "doctype_event": "Before Save",
        "enabled": 1,
        "script": script_body,
    }
    update_doc = {
        "script_type": "DocType Event",
        "reference_doctype": "Item",
        "doctype_event": "Before Save",
        "enabled": 1,
        "script": script_body,
    }

    try:
        result = client.upsert_doc("Server Script", script_name, create_doc, update_doc)
        print(f"- {script_name}: {result}")
    except Exception as e:
        print("- Could not upsert Server Script. This usually means Server Scripts are disabled.")
        print(f"  Error: {e}")


def ensure_invoice_notification(client: ERPClient) -> None:
    print("\n[Notifications]")
    name = "Auto Send Sales Invoice to Customer"

    primary_payload = {
        "name": name,
        "enabled": 1,
        "document_type": "Sales Invoice",
        "event": "Submit",
        "subject": "Invoice {{ doc.name }}",
        "message": (
            "Hi {{ doc.customer_name }},<br><br>"
            "Invoice {{ doc.name }} for {{ doc.grand_total }} is ready.<br>"
            "Due date: {{ doc.due_date }}<br><br>"
            "Thank you."
        ),
        "channel": "Email",
        "send_system_notification": 0,
        "attach_print": 1,
        "recipients": [
            {"receiver_by_document_field": "contact_email"},
        ],
    }

    # Fallback payload for ERP versions that do not accept some newer fields.
    fallback_payload = {
        "name": name,
        "enabled": 1,
        "document_type": "Sales Invoice",
        "event": "Submit",
        "subject": "Invoice {{ doc.name }}",
        "message": (
            "Hi {{ doc.customer_name }},<br><br>"
            "Invoice {{ doc.name }} for {{ doc.grand_total }} is ready.<br>"
            "Due date: {{ doc.due_date }}<br><br>"
            "Thank you."
        ),
        "recipients": [{"receiver_by_document_field": "contact_email"}],
    }

    try:
        result = client.upsert_doc("Notification", name, primary_payload, dict(primary_payload))
        print(f"- {name}: {result}")
    except Exception as e:
        print(f"- Primary notification payload failed, retrying with fallback: {e}")
        try:
            result = client.upsert_doc("Notification", name, fallback_payload, dict(fallback_payload))
            print(f"- {name}: {result}")
        except Exception as e2:
            print(f"- {name}: failed ({e2})")


def parse_sql_templates() -> dict[str, str]:
    raw = SQL_TEMPLATES_PATH.read_text(encoding="utf-8")
    mapping: dict[str, str] = {}

    current_title = None
    current_lines: list[str] = []
    header_re = re.compile(r"^--\s+(\d+\)\s+.+)$")

    for line in raw.splitlines():
        m = header_re.match(line)
        if m:
            if current_title and current_lines:
                mapping[current_title] = "\n".join(current_lines).strip() + "\n"
            current_title = m.group(1).strip()
            current_lines = []
            continue

        if current_title is None:
            continue
        if line.startswith("--"):
            continue
        current_lines.append(line)

    if current_title and current_lines:
        mapping[current_title] = "\n".join(current_lines).strip() + "\n"

    # Keep only query sections that begin with SELECT.
    cleaned = {k: v for k, v in mapping.items() if v.lstrip().upper().startswith("SELECT")}
    if not cleaned:
        raise RuntimeError("Failed to parse SQL templates into query sections.")
    return cleaned


def ensure_reports(client: ERPClient) -> None:
    print("\n[Query Reports]")
    queries = parse_sql_templates()

    report_specs = [
        ("Dashboard Daily Sales 30d", "Sales Invoice", "1) Daily Sales (last 30 days)"),
        ("Dashboard Top 10 Items Revenue", "Sales Invoice", "2) Top 10 Items by Revenue (this month)"),
        ("Dashboard Overdue Invoices", "Sales Invoice", "3) Overdue Invoices table"),
        ("Dashboard Recurring Invoices Due", "Auto Repeat", "4) Recurring invoices due in next 7 days"),
        ("Dashboard Receivables Aging", "Sales Invoice", "5) Receivables aging snapshot by customer"),
    ]

    for report_name, ref_doctype, query_key in report_specs:
        query = queries[query_key]
        create_doc = {
            "name": report_name,
            "report_name": report_name,
            "ref_doctype": ref_doctype,
            "report_type": "Query Report",
            "is_standard": "No",
            "query": query,
            "module": "Accounts",
            "prepared_report": 0,
            "disabled": 0,
        }
        update_doc = {
            "ref_doctype": ref_doctype,
            "report_type": "Query Report",
            "is_standard": "No",
            "query": query,
            "module": "Accounts",
            "prepared_report": 0,
            "disabled": 0,
        }

        try:
            result = client.upsert_doc("Report", report_name, create_doc, update_doc)
            print(f"- {report_name}: {result}")
        except Exception as e:
            print(f"- {report_name}: failed ({e})")


def ensure_dashboard_charts(client: ERPClient) -> None:
    print("\n[Dashboard Charts]")
    charts = [
        ("Daily Sales 30d", "Line", "Dashboard Daily Sales 30d"),
        ("Top 10 Items Revenue", "Bar", "Dashboard Top 10 Items Revenue"),
        ("Overdue Invoices", "Bar", "Dashboard Overdue Invoices"),
    ]

    for chart_name, chart_type, report_name in charts:
        create_doc = {
            "name": chart_name,
            "chart_name": chart_name,
            "module": "Accounts",
            "is_standard": 0,
            "chart_type": "Report",
            "report_name": report_name,
            "use_report_chart": 1,
            "type": chart_type,
            "is_public": 1,
            "timeseries": 0,
            "time_interval": "Daily",
            "filters_json": "{}",
            "dynamic_filters_json": "{}",
        }
        update_doc = {
            "module": "Accounts",
            "is_standard": 0,
            "chart_type": "Report",
            "report_name": report_name,
            "use_report_chart": 1,
            "type": chart_type,
            "is_public": 1,
            "timeseries": 0,
            "time_interval": "Daily",
            "filters_json": "{}",
            "dynamic_filters_json": "{}",
        }

        try:
            result = client.upsert_doc("Dashboard Chart", chart_name, create_doc, update_doc)
            print(f"- {chart_name}: {result}")
        except Exception as e:
            print(f"- {chart_name}: failed ({e})")


def main() -> None:
    print(f"ERPNext URL: {ERPNEXT_URL}")
    client = ERPClient(ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET)

    client.ping()
    print("Connected to ERPNext API.")

    ensure_custom_fields(client)
    ensure_server_script(client)
    ensure_invoice_notification(client)
    ensure_reports(client)
    ensure_dashboard_charts(client)

    print("\nDone. Core dashboard customization has been applied where API permissions allowed.")


if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    main()
