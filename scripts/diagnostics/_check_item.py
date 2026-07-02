import requests
requests.packages.urllib3.disable_warnings()
s = requests.Session(); s.verify = False
s.post('https://www.karavanimports.com/api/method/login', data={'usr':'Administrator','pwd':'TempMigrate2026!'}, timeout=15)

users = s.get('https://www.karavanimports.com/api/resource/User',
    params={"fields": '["name","full_name"]', "limit": 20,
            "filters": '[["user_type","=","System User"],["name","!=","Guest"]]'},
    timeout=15).json().get('data', [])
print("System users:")
for u in users:
    print(" ", u.get('name'), "|", u.get('full_name'))

target = next((u['name'] for u in users if 'youssef' in u['name'].lower()), None)
if not target:
    target = next((u['name'] for u in users if u['name'] != 'Administrator'), 'Administrator')
print(f"\nSetting connected_user to: {target}")

r = s.put('https://www.karavanimports.com/api/resource/Email%20Account/Karavan%20Imports',
          json={"connected_user": target}, timeout=15)
print(f"Update: {r.status_code}")
ea = s.get('https://www.karavanimports.com/api/resource/Email%20Account/Karavan%20Imports', timeout=15).json().get('data', {})
print(f"connected_user now: {ea.get('connected_user')}")
