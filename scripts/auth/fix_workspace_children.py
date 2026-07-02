import os
"""
Fix: re-push all workspace child table rows (shortcuts, links, charts, number cards)
from POC to prod. The previous migration saved content JSON but Frappe's child table
save requires rows to have no `name` field (so Frappe creates new rows instead of
trying to update non-existent POC-named rows).
"""

import requests, json, time

requests.packages.urllib3.disable_warnings()

POC_URL  = "http://3.216.86.193"
PROD_URL = "https://www.karavanimports.com"
PASS     = os.environ.get("ERP_ADMIN_PWD")

def make_session(url):
    s = requests.Session()
    s.verify = False
    r = s.post(f"{url}/api/method/login", data={"usr": "Administrator", "pwd": PASS}, timeout=20)
    assert r.json().get("message") == "Logged In", f"Login failed: {r.text[:100]}"
    print(f"  Logged in to {url}")
    return s

def get_workspace(session, url, name):
    r = session.get(f"{url}/api/resource/Workspace/{requests.utils.quote(name)}", timeout=30)
    r.raise_for_status()
    return r.json().get("data", {})

def strip_child_names(rows):
    """Remove name/parent/parenttype/parentfield so Frappe creates new rows."""
    clean = []
    for row in rows:
        r = {k: v for k, v in row.items()
             if k not in ("name", "creation", "modified", "modified_by", "owner",
                          "parent", "parenttype", "parentfield")}
        clean.append(r)
    return clean

def push_workspace(session, url, name, poc_data):
    payload = {
        "content":      poc_data.get("content"),
        "shortcuts":    strip_child_names(poc_data.get("shortcuts", [])),
        "links":        strip_child_names(poc_data.get("links", [])),
        "charts":       strip_child_names(poc_data.get("charts", [])),
        "number_cards": strip_child_names(poc_data.get("number_cards", [])),
        "quick_lists":  strip_child_names(poc_data.get("quick_lists", [])),
        "custom_blocks":strip_child_names(poc_data.get("custom_blocks", [])),
    }
    r = session.put(f"{url}/api/resource/Workspace/{requests.utils.quote(name)}",
                    json=payload, timeout=30)
    r.raise_for_status()
    return r.json().get("data", {})

print("Logging in...")
poc  = make_session(POC_URL)
prod = make_session(PROD_URL)

print("\nFetching workspace list from POC...")
ws_list_r = poc.get(f"{POC_URL}/api/resource/Workspace", params={"limit": 200, "fields": '["name"]'})
ws_names = [w["name"] for w in ws_list_r.json().get("data", [])]
print(f"  {len(ws_names)} workspaces\n")

ok = 0
fail = 0
for name in ws_names:
    try:
        poc_ws = get_workspace(poc, POC_URL, name)
        sc = len(poc_ws.get("shortcuts", []))
        lk = len(poc_ws.get("links", []))

        result = push_workspace(prod, PROD_URL, name, poc_ws)

        # Verify what actually got saved
        saved_sc = len(result.get("shortcuts", []))
        saved_lk = len(result.get("links", []))

        status = "OK" if (saved_sc == sc and saved_lk == lk) else f"MISMATCH(sc:{sc}->{saved_sc} lk:{lk}->{saved_lk})"
        print(f"  [{name}] {sc} shortcuts, {lk} links -> {status}")
        ok += 1
    except Exception as e:
        print(f"  [{name}] FAIL: {str(e)[:120]}")
        fail += 1
    time.sleep(0.1)

print(f"\nDone: {ok} OK, {fail} failed")
