import requests, json
requests.packages.urllib3.disable_warnings()
s = requests.Session(); s.verify = False
s.post('https://www.karavanimports.com/api/method/login', data={'usr':'Administrator','pwd':'TempMigrate2026!'}, timeout=15)

apps = s.get('https://www.karavanimports.com/api/resource/Connected%20App',
             params={"fields": '["name","provider_name","client_id","redirect_uri","authorization_uri"]', "limit": 10},
             timeout=15).json()
print("Connected Apps:")
for a in apps.get('data', []):
    print(" ", json.dumps(a, indent=4))

# Get the most recent one
if apps.get('data'):
    name = apps['data'][0]['name']
    full = s.get(f'https://www.karavanimports.com/api/resource/Connected%20App/{name}', timeout=15).json().get('data', {})
    print("\nFull Connected App:")
    print("  redirect_uri:", full.get('redirect_uri'))
    print("  authorization_uri:", full.get('authorization_uri'))
    print("  client_id:", full.get('client_id', '')[:40], "...")
    print("  scopes:", full.get('scopes'))
