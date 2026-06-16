import json
import urllib.parse

import requests

BASE = "http://3.216.86.193"
TOKEN = "token 647f56b706a1bea:6c615d3ea8cbd4d"
SOURCE_WORKSPACE = "Operations Cockpit"
ALIAS_WORKSPACE = "Main Operations"

session = requests.Session()
session.verify = False
session.headers.update({"Authorization": TOKEN, "Content-Type": "application/json"})


def get_workspace(name: str):
    return session.get(
        f"{BASE}/api/resource/Workspace/{urllib.parse.quote(name)}",
        timeout=30,
    )


def clean_shortcut(row: dict) -> dict:
    keys = ["label", "type", "link_to", "url", "doc_view", "stats_filter", "color"]
    return {k: row.get(k) for k in keys if row.get(k) not in (None, "")}


def clean_chart(row: dict) -> dict:
    keys = ["label", "chart_name", "width"]
    return {k: row.get(k) for k in keys if row.get(k) not in (None, "")}


def clean_link(row: dict) -> dict:
    keys = ["label", "type", "link_to", "hidden"]
    return {k: row.get(k) for k in keys if row.get(k) is not None}


def ensure_main_operations_alias() -> None:
    src = get_workspace(SOURCE_WORKSPACE)
    if src.status_code != 200:
        raise RuntimeError(f"Source workspace not found: {src.status_code} {src.text[:300]}")

    alias = get_workspace(ALIAS_WORKSPACE)
    if alias.status_code == 200:
        print(f"Alias already exists: {ALIAS_WORKSPACE}")
        return

    source_doc = src.json().get("data", {})
    payload = {
        "doctype": "Workspace",
        "title": ALIAS_WORKSPACE,
        "label": ALIAS_WORKSPACE,
        "module": source_doc.get("module") or "Selling",
        "public": 1,
        "is_hidden": 0,
        "icon": source_doc.get("icon") or "home",
        "indicator_color": source_doc.get("indicator_color") or "green",
        "content": source_doc.get("content") or "[]",
        "links": [clean_link(x) for x in (source_doc.get("links") or [])],
        "shortcuts": [clean_shortcut(x) for x in (source_doc.get("shortcuts") or [])],
        "charts": [clean_chart(x) for x in (source_doc.get("charts") or [])],
    }

    created = session.post(f"{BASE}/api/resource/Workspace", data=json.dumps(payload), timeout=60)
    if created.status_code >= 400:
        raise RuntimeError(f"Alias create failed: {created.status_code} {created.text[:1200]}")

    print(f"Alias created: {ALIAS_WORKSPACE}")


def set_default_workspace(user: str, workspace_name: str) -> None:
    result = session.put(
        f"{BASE}/api/resource/User/{urllib.parse.quote(user)}",
        data=json.dumps({"default_workspace": workspace_name}),
        timeout=30,
    )
    if result.status_code >= 400:
        raise RuntimeError(f"User update failed: {result.status_code} {result.text[:600]}")
    print(f"Default workspace for {user} -> {workspace_name}")


if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    ensure_main_operations_alias()
    set_default_workspace("Administrator", ALIAS_WORKSPACE)
