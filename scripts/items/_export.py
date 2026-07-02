import frappe, json, os, re, shutil

SITE = 'frontend'
OUT = '/tmp/migrate'
FILES_OUT = os.path.join(OUT, 'files')

frappe.init(site=SITE)
frappe.connect()

DROP = {'creation','modified','modified_by','owner','docstatus','idx',
        '_user_tags','_comments','_assign','_liked_by','lft','rgt','_seen',
        'parent','parentfield','parenttype'}

def scrub(v, top=False):
    if isinstance(v, dict):
        out = {}
        for k, val in v.items():
            if k in DROP and not (top and k == 'name'):
                continue
            out[k] = scrub(val)
        return out
    if isinstance(v, list):
        return [scrub(x) for x in v]
    return v

# (doctype, filters)  -- filters limit to custom/non-standard where applicable
EXPORTS = [
    ('Role', {}),
    ('Module Profile', {}),
    ('Role Profile', {}),
    ('Custom Field', {}),
    ('Property Setter', {}),
    ('Report', {'is_standard': 'No'}),
    ('Print Format', {'standard': 'No'}),
    ('Letter Head', {}),
    ('Client Script', {}),
    ('Server Script', {}),
    ('Number Card', {'is_standard': 0}),
    ('Dashboard Chart', {'is_standard': 0}),
    ('Dashboard', {'is_standard': 0}),
    ('Web Template', {'standard': 0}),
    ('Web Page', {}),
    ('Web Form', {'is_standard': 0}),
    ('Notification', {}),
    ('Workspace', {}),
]

bundle = {'source_site': SITE, 'doctypes': {}}
for dt, filters in EXPORTS:
    try:
        names = [r['name'] for r in frappe.get_all(dt, filters=filters, fields=['name'], limit_page_length=0)]
    except Exception as e:
        bundle['doctypes'][dt] = {'_error': str(e)[:120]}
        print(f'{dt}: ERROR {str(e)[:80]}')
        continue
    docs = []
    for n in names:
        try:
            d = frappe.get_doc(dt, n).as_dict()
            docs.append(scrub(d, top=True))
        except Exception as e:
            print(f'  skip {dt}/{n}: {str(e)[:60]}')
    bundle['doctypes'][dt] = docs
    print(f'{dt}: {len(docs)}')

# Singles (branding)
singles = {}
for sdt, keys in [
    ('Website Settings', ['app_name','app_logo','banner_image','favicon','splash_image',
                          'website_theme','brand_html','footer_logo','footer_powered',
                          'hide_footer_signup','title_prefix','copyright']),
    ('Navbar Settings', ['app_logo','logo_width']),
]:
    try:
        doc = frappe.get_single(sdt).as_dict()
        singles[sdt] = {k: doc.get(k) for k in keys if k in doc}
    except Exception as e:
        singles[sdt] = {'_error': str(e)[:120]}
bundle['singles'] = singles
print('singles:', json.dumps(singles)[:300])

# Collect logo/image file paths referenced by branding
urls = set()
ws = singles.get('Website Settings', {})
for k in ['app_logo','banner_image','favicon','splash_image','footer_logo']:
    v = ws.get(k)
    if isinstance(v, str) and ('/files/' in v):
        urls.add(v)
bh = ws.get('brand_html') or ''
for m in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', bh):
    if '/files/' in m:
        urls.add(m)
nb = singles.get('Navbar Settings', {})
if isinstance(nb.get('app_logo'), str) and '/files/' in nb['app_logo']:
    urls.add(nb['app_logo'])

# also grab any File docs whose file_url is one of these (for File doc recreation)
site_path = frappe.get_site_path()  # .../sites/frontend
copied = []
file_meta = []
for u in sorted(urls):
    rel = u.split('?')[0]
    if rel.startswith('/private/files/'):
        src = os.path.join(site_path, 'private', 'files', rel[len('/private/files/'):])
        sub = os.path.join('private', rel[len('/private/'):])
    elif rel.startswith('/files/'):
        src = os.path.join(site_path, 'public', 'files', rel[len('/files/'):])
        sub = os.path.join('public', rel[len('/'):])
    else:
        continue
    dst = os.path.join(FILES_OUT, sub)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        copied.append((u, sub))
    else:
        print(f'  MISSING file on disk: {src}')
    # File doc
    fd = frappe.get_all('File', filters={'file_url': rel}, fields=['name','file_name','is_private','file_url','folder','attached_to_doctype','attached_to_name'], limit_page_length=1)
    if fd:
        file_meta.append(fd[0])

bundle['files'] = [{'url': u, 'path': s} for u, s in copied]
bundle['file_docs'] = scrub(file_meta)
print('files copied:', copied)

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'bundle.json'), 'w') as f:
    json.dump(bundle, f, indent=1, default=str)
print('BUNDLE_WRITTEN', os.path.join(OUT, 'bundle.json'))
