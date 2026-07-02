import os, requests, json
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/resource/Print Format",
          params={"filters": '[["doc_type","=","Sales Invoice"]]',
                  "fields": '["name","standard","disabled"]',
                  "limit": 20}, timeout=15)
formats = r.json().get("data", [])
print("Print formats for Sales Invoice:")
for f in formats:
    print(" ", f)

# Get the HTML of the first custom one
for f in formats:
    if not f.get("standard"):
        detail = s.get(f"{URL}/api/resource/Print Format/{f['name']}", timeout=15).json().get("data", {})
        print(f"\n=== {f['name']} ===")
        print("css:", detail.get("css", "")[:300])
        print("html:", detail.get("html", "")[:2000])
        break
