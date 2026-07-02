import os
"""
Compares and fixes Standard Selling prices in ERPNext against Data_06_23.csv.
CSV columns: UPCcode, Expandeddescription, Branddescription, Price (sell), Activeprice
"""
import requests, csv, difflib, re

requests.packages.urllib3.disable_warnings()

BASE = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f'{BASE}/api/method/login', data={'usr':'Administrator','pwd':os.environ.get('ERP_ADMIN_PWD')}, timeout=15)

# ── 1. Load CSV (POS data) ───────────────────────────────────────────────────
def norm_upc(u):
    return re.sub(r'[`\s]', '', str(u)).lstrip('0')

csv_by_upc  = {}
csv_by_name = []

with open('Data_06_23.csv', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        raw_price = row.get('Price') or row.get('Activeprice') or ''
        if not raw_price or raw_price.strip() in ('NULL', ''):
            continue
        try:
            price = float(raw_price.strip())
        except:
            continue
        if price <= 0:
            continue
        name  = (row.get('Expandeddescription') or row.get('POSdescription') or '').strip()
        brand = (row.get('Branddescription') or '').strip()
        upc   = norm_upc(row.get('UPCcode') or '')
        entry = {'name': name, 'brand': brand, 'upc': upc, 'price': price}
        if upc:
            csv_by_upc.setdefault(upc, []).append(entry)
        if name:
            csv_by_name.append(entry)

print(f'CSV rows with price: {len(csv_by_name)}  |  unique UPCs: {len(csv_by_upc)}')

# ── 2. Load ERPNext items + barcodes + current prices ────────────────────────
report = s.get(f'{BASE}/api/method/frappe.desk.query_report.run',
    params={'report_name': 'Inventory Manager', 'ignore_prepared_report': 1},
    timeout=60).json().get('message', {})

erp_items = {}
for row in report.get('result', []):
    if not isinstance(row, dict): continue
    code = row.get('item_id','')
    if not code: continue
    erp_items[code] = {
        'name':   row.get('description',''),
        'brand':  row.get('brand',''),
        'upc':    norm_upc(str(row.get('upc_/_barcode') or '')),
        'price':  float(row.get('price/item') or 0),
    }
print(f'ERPNext items: {len(erp_items)}')

# ── 3. Match each ERPNext item to best CSV price ──────────────────────────────
csv_name_lower = [r['name'].lower() for r in csv_by_name]

def find_csv_price(erp_upc, erp_name):
    if erp_upc and erp_upc in csv_by_upc:
        return csv_by_upc[erp_upc][0]['price'], f'upc:{erp_upc}'
    matches = difflib.get_close_matches(erp_name.lower(), csv_name_lower, n=1, cutoff=0.72)
    if matches:
        idx = csv_name_lower.index(matches[0])
        return csv_by_name[idx]['price'], f'name~{csv_by_name[idx]["name"][:35]}'
    return None, None

to_update  = []
already_ok = []
no_match   = []

for code, info in sorted(erp_items.items()):
    csv_price, method = find_csv_price(info['upc'], info['name'])
    if csv_price is None:
        no_match.append((code, info['name'], info['price']))
    elif abs(csv_price - info['price']) > 0.005:
        to_update.append((code, info['price'], csv_price, method))
    else:
        already_ok.append(code)

print(f'\nAlready correct : {len(already_ok)}')
print(f'Need update     : {len(to_update)}')
print(f'No CSV match    : {len(no_match)}')

if to_update:
    print('\nMISMATCHES to fix:')
    for code, old, new, method in to_update:
        print(f'  {code:12}  ${old:.2f} -> ${new:.2f}  [{method}]')

if no_match:
    print('\nNO MATCH (kept as-is):')
    for code, name, price in no_match:
        print(f'  {code:12}  ${price:.2f}  {name[:55]}')

# ── 4. Apply updates ──────────────────────────────────────────────────────────
if to_update:
    print('\nApplying updates...')
    ok = 0; fail = 0
    for code, old_p, new_p, method in to_update:
        existing = s.get(f'{BASE}/api/resource/Item%20Price',
            params={'filters': f'[["item_code","=","{code}"],["price_list","=","Standard Selling"]]',
                    'fields': '["name"]', 'limit': 1},
            timeout=15).json().get('data', [])
        if existing:
            r = s.put(f'{BASE}/api/resource/Item%20Price/{existing[0]["name"]}',
                      json={'price_list_rate': new_p}, timeout=15)
        else:
            r = s.post(f'{BASE}/api/resource/Item%20Price',
                json={'item_code': code, 'price_list': 'Standard Selling',
                      'price_list_rate': new_p, 'selling': 1}, timeout=15)
        if r.status_code in (200, 201):
            ok += 1
        else:
            fail += 1
            print(f'  FAIL {code}: {r.text[:100]}')
    print(f'Done: {ok} updated, {fail} failed.')
else:
    print('\nAll prices already correct.')
