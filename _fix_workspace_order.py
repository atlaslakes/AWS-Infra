import requests, json
requests.packages.urllib3.disable_warnings()
s = requests.Session(); s.verify = False
s.post('https://www.karavanimports.com/api/method/login', data={'usr':'Administrator','pwd':'TempMigrate2026!'}, timeout=15)

ws = s.get('https://www.karavanimports.com/api/resource/Workspace/Stock', timeout=15).json().get('data', {})
skip = {'name','creation','modified','modified_by','owner','parent','parenttype','parentfield'}
def strip(rows): return [{k:v for k,v in r.items() if k not in skip} for r in rows]

content = json.loads(ws.get('content') or '[]')

# Pull out our two misplaced shortcuts
our_labels = {'Inventory Manager', 'Expiry Tracking'}
misplaced = [c for c in content if c.get('type') == 'shortcut'
             and c.get('data', {}).get('shortcut_name') in our_labels]
rest = [c for c in content if not (c.get('type') == 'shortcut'
        and c.get('data', {}).get('shortcut_name') in our_labels)]

# Find the header that precedes the main shortcuts block
header_idx = next(i for i, c in enumerate(rest) if c.get('type') == 'header')

# Insert our shortcuts right after that header
reordered = rest[:header_idx + 1] + misplaced + rest[header_idx + 1:]

print("New content order:")
for i, c in enumerate(reordered):
    d = c.get('data', {})
    name = d.get('shortcut_name') or d.get('label') or d.get('chart_name') or '-'
    print(f"  [{i}] {c.get('type'):12s}  {c.get('id','?'):12s}  {name}")

r = s.put('https://www.karavanimports.com/api/resource/Workspace/Stock', json={
    'shortcuts': strip(ws.get('shortcuts', [])),
    'links':     strip(ws.get('links', [])),
    'content':   json.dumps(reordered),
}, timeout=20)
print("\nPUT:", r.status_code)

# Clear cache
s.post('https://www.karavanimports.com/api/method/frappe.sessions.clear', timeout=15)
print("Cache cleared.")
