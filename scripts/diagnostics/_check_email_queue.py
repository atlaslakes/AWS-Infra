import os, requests
import urllib3; urllib3.disable_warnings()

URL = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)

r = s.get(f"{URL}/api/resource/Email Queue",
          params={"fields": '["name","sender","recipients","status","error","creation"]',
                  "limit": 5, "order_by": "creation desc"}, timeout=15)
rows = r.json().get("data", [])
for row in rows:
    print(f"--- {row['name']} ---")
    print(f"  From:    {row.get('sender')}")
    print(f"  To:      {row.get('recipients')}")
    print(f"  Status:  {row.get('status')}")
    print(f"  Error:   {row.get('error')}")
    print()
