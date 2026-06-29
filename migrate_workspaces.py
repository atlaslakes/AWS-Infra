import os
"""
Migrates all Workspace shortcuts, link cards, charts, and number cards
from POC (3.216.86.193) to production (www.karavanimports.com).
"""

import requests
import json
import sys

POC_URL = "http://3.216.86.193"
PROD_URL = "https://www.karavanimports.com"
ADMIN_PASS = os.environ.get("ERP_ADMIN_PWD")

session_poc = requests.Session()
session_poc.verify = False
session_prod = requests.Session()
session_prod.verify = False

requests.packages.urllib3.disable_warnings()


def login(session, url, password):
    r = session.post(f"{url}/api/method/login", data={
        "usr": "Administrator",
        "pwd": password
    })
    r.raise_for_status()
    data = r.json()
    if data.get("message") != "Logged In":
        raise Exception(f"Login failed: {data}")
    print(f"  Logged in to {url}")


def get_all_workspaces(session, url):
    r = session.get(f"{url}/api/resource/Workspace", params={
        "limit": 200,
        "fields": '["name"]'
    })
    r.raise_for_status()
    return [w["name"] for w in r.json().get("data", [])]


def get_workspace(session, url, name):
    r = session.get(f"{url}/api/resource/Workspace/{requests.utils.quote(name)}", params={
        "fields": '["*"]'
    })
    r.raise_for_status()
    return r.json().get("data", {})


def update_workspace(session, url, name, data):
    # Only push the fields that hold shortcuts/links/content
    payload = {
        "content": data.get("content"),
        "shortcuts": data.get("shortcuts", []),
        "links": data.get("links", []),
        "charts": data.get("charts", []),
        "number_cards": data.get("number_cards", []),
        "quick_lists": data.get("quick_lists", []),
        "custom_blocks": data.get("custom_blocks", []),
    }
    r = session.put(
        f"{url}/api/resource/Workspace/{requests.utils.quote(name)}",
        json=payload
    )
    if r.status_code == 404:
        # workspace doesn't exist on prod — create it
        create_payload = {k: v for k, v in data.items()
                          if k not in ("name", "creation", "modified", "modified_by", "owner")}
        r = session.post(f"{url}/api/resource/Workspace", json=create_payload)
    r.raise_for_status()
    return r.json()


print("=== Workspace Migration: POC to Prod ===\n")

print("Logging in...")
login(session_poc, POC_URL, ADMIN_PASS)
login(session_prod, PROD_URL, ADMIN_PASS)

print("\nFetching workspace list from POC...")
ws_names = get_all_workspaces(session_poc, POC_URL)
print(f"  Found {len(ws_names)} workspaces: {ws_names}\n")

success = 0
failed = []

for name in ws_names:
    try:
        print(f"  [{name}] Reading from POC...", end=" ")
        ws_data = get_workspace(session_poc, POC_URL, name)
        shortcuts = ws_data.get("shortcuts", [])
        links = ws_data.get("links", [])
        print(f"{len(shortcuts)} shortcuts, {len(links)} links -> ", end="")

        print("Writing to prod...", end=" ")
        update_workspace(session_prod, PROD_URL, name, ws_data)
        print("OK")
        success += 1
    except Exception as e:
        print(f"FAILED: {e}")
        failed.append((name, str(e)))

print(f"\n=== Done: {success} succeeded, {len(failed)} failed ===")
if failed:
    print("Failed workspaces:")
    for name, err in failed:
        print(f"  - {name}: {err}")
