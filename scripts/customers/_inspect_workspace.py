import requests, json
requests.packages.urllib3.disable_warnings()
s = requests.Session(); s.verify = False
s.post('https://www.karavanimports.com/api/method/login', data={'usr':'Administrator','pwd':'TempMigrate2026!'}, timeout=15)

ws = s.get('https://www.karavanimports.com/api/resource/Workspace/Stock', timeout=15).json().get('data', {})
content  = json.loads(ws.get('content') or '[]')
shortcuts = ws.get('shortcuts', [])

print("shortcuts count:", len(shortcuts))
print("content count:  ", len(content))
print()
print("=== content order ===")
for i, c in enumerate(content):
    d = c.get('data', {})
    name = d.get('shortcut_name') or d.get('label') or d.get('chart_name') or "-"
    print(f"  [{i}] type={c.get('type'):12s}  id={c.get('id','MISSING'):12s}  name={name}")

print()
print("=== shortcut definitions for our entries ===")
for sc in shortcuts:
    if sc.get('label') in ('Inventory Manager', 'Expiry Tracking'):
        clean = {k: v for k, v in sc.items()
                 if k not in ('name','creation','modified','owner','parent','parenttype','parentfield','idx')}
        print(" ", json.dumps(clean, indent=4))

# Also call clear cache
print()
print("Clearing Frappe cache...")
r = s.post('https://www.karavanimports.com/api/method/frappe.sessions.clear', timeout=15)
print("clear_cache:", r.status_code)
