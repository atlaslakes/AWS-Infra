import frappe, json
frappe.init(site='frontend')
frappe.connect()

doctypes = [
    'Workspace', 'Custom Field', 'Property Setter', 'Client Script', 'Server Script',
    'Print Format', 'Notification', 'Role', 'Role Profile', 'Module Profile',
    'Dashboard', 'Dashboard Chart', 'Number Card', 'Custom HTML Block',
    'Web Page', 'Website Theme', 'Letter Head', 'Web Template', 'Web Form',
    'Report', 'Kanban Board', 'Dashboard Chart Source', 'Custom DocPerm',
    'Workspace Link', 'Page',
]
out = {}
for dt in doctypes:
    try:
        out[dt] = frappe.db.count(dt)
    except Exception as e:
        out[dt] = 'ERR:' + str(e)[:60]

# Singles relevant to look & feel
try:
    ws = frappe.get_single('Website Settings').as_dict()
    out['_WebsiteSettings'] = {k: ws.get(k) for k in
        ['app_name','app_logo','banner_image','favicon','splash_image','website_theme','brand_html','footer_logo'] if k in ws}
except Exception as e:
    out['_WebsiteSettings'] = 'ERR:' + str(e)[:60]
try:
    nb = frappe.get_single('Navbar Settings').as_dict()
    out['_NavbarSettings_app_logo'] = nb.get('app_logo')
except Exception as e:
    out['_NavbarSettings'] = 'ERR:' + str(e)[:60]
try:
    out['_WebsiteThemes'] = frappe.get_all('Website Theme', fields=['name','custom_scss','custom'])
except Exception as e:
    out['_WebsiteThemes'] = 'ERR:' + str(e)[:60]
try:
    out['_Workspaces'] = frappe.get_all('Workspace', fields=['name','title','public','for_user'])
except Exception as e:
    out['_Workspaces'] = 'ERR:' + str(e)[:60]

print('INVENTORY_JSON_START')
print(json.dumps(out, indent=2, default=str))
print('INVENTORY_JSON_END')
