import os, requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/resource/Print Format/Atlas Invoice Tracking Classic", timeout=15)
html = r.json()["data"]["html"]

# Fix T&C margin — it's pinned to bottom with no side padding
# Current:
#   .btm-terms { position: fixed; bottom: 12mm; left: 0; right: 0; ... padding-top: 6px; }
# Add left/right margin to match page margins (9mm)
html = html.replace(
    'position: fixed; bottom: 12mm; left: 0; right: 0;',
    'position: fixed; bottom: 12mm; left: 9mm; right: 9mm;'
)

resp = s.put(f"{URL}/api/resource/Print Format/Atlas Invoice Tracking Classic",
             json={"doctype": "Print Format",
                   "name": "Atlas Invoice Tracking Classic",
                   "html": html}, timeout=30)
print("Updated:", resp.status_code, "OK" if resp.status_code in (200, 201) else resp.text[:200])
