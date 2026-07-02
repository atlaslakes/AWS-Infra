import frappe, json, os, shutil, sys

SITE = 'frontend'
BUNDLE = '/tmp/migrate'
PHASE = sys.argv[1] if len(sys.argv) > 1 else 'all'   # 'pre' | 'post' | 'all'

frappe.init(site=SITE)
frappe.connect()

DROP = {'creation','modified','modified_by','owner','docstatus','idx',
        '_user_tags','_comments','_assign','_liked_by','lft','rgt','_seen',
        'parent','parentfield','parenttype'}

def clean(d):
    return {k: v for k, v in d.items() if k not in DROP}

PRE_ORDER = ['Role','Module Profile','Role Profile','Custom Field','Property Setter',
             'Report','Print Format','Letter Head','Client Script','Server Script',
             'Number Card','Dashboard Chart','Dashboard','Web Template','Web Page',
             'Web Form','Notification']
POST_ORDER = ['Workspace']

bundle = json.load(open(os.path.join(BUNDLE, 'bundle.json')))
docs_by = bundle['doctypes']

def import_dt(dt):
    docs = docs_by.get(dt) or []
    if not isinstance(docs, list):
        print(f'{dt}: SKIP ({docs})'); return
    c = u = f = 0
    for raw in docs:
        name = raw.get('name')
        data = clean(raw); data['doctype'] = dt
        try:
            if name and frappe.db.exists(dt, name):
                ex = frappe.get_doc(dt, name)
                ex.update(data)
                ex.flags.ignore_permissions = True
                ex.flags.ignore_mandatory = True
                ex.flags.ignore_links = True
                ex.save(ignore_permissions=True)
                u += 1
            else:
                d = frappe.get_doc(data)
                d.flags.ignore_permissions = True
                d.flags.ignore_mandatory = True
                d.flags.ignore_links = True
                d.insert(ignore_permissions=True, set_name=name)
                c += 1
        except Exception as e:
            f += 1
            print(f'  FAIL {dt}/{name}: {str(e)[:160]}')
    frappe.db.commit()
    print(f'{dt}: created={c} updated={u} failed={f}')

def restore_files_and_singles():
    site_path = frappe.get_site_path()
    for fe in bundle.get('files', []):
        sub = fe['path']
        src = os.path.join(BUNDLE, 'files', sub)
        if sub.startswith('public/'):
            dst = os.path.join(site_path, 'public', sub[len('public/'):])
        elif sub.startswith('private/'):
            dst = os.path.join(site_path, 'private', sub[len('private/'):])
        else:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(src):
            shutil.copy2(src, dst); print('file ->', dst)
        else:
            print('  missing in bundle:', src)
    for fd in bundle.get('file_docs', []):
        try:
            if fd.get('file_url') and not frappe.db.exists('File', {'file_url': fd['file_url']}):
                nd = frappe.get_doc({'doctype': 'File', **clean(fd)})
                nd.flags.ignore_permissions = True
                nd.insert(ignore_permissions=True)
                print('File doc created', fd['file_url'])
        except Exception as e:
            print('  file doc fail:', str(e)[:120])
    for sdt, vals in bundle.get('singles', {}).items():
        try:
            s = frappe.get_single(sdt)
            for k, v in vals.items():
                if k.startswith('_'):
                    continue
                s.set(k, v)
            s.flags.ignore_permissions = True
            s.save(ignore_permissions=True)
            print('single saved:', sdt)
        except Exception as e:
            print('  single fail', sdt, str(e)[:140])
    frappe.db.commit()

if PHASE in ('pre', 'all'):
    for dt in PRE_ORDER:
        import_dt(dt)
if PHASE in ('post', 'all'):
    for dt in POST_ORDER:
        import_dt(dt)
    restore_files_and_singles()

print('IMPORT_DONE phase=' + PHASE)
