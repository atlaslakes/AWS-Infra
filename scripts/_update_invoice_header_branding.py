import requests

BASE = "http://3.216.86.193"
API_KEY = "647f56b706a1bea"
API_SECRET = "6c615d3ea8cbd4d"
FORMAT_NAME = "Atlas Invoice Classic"
INVOICE_NAME = "ACC-SINV-2026-00007"

session = requests.Session()
session.headers.update({"Authorization": f"token {API_KEY}:{API_SECRET}"})


def safe_get(path: str):
    r = session.get(f"{BASE}{path}", timeout=30)
    if r.status_code >= 400:
        return None
    try:
        return r.json().get("data")
    except Exception:
        return None


logo = None
ws = safe_get("/api/resource/Website Settings/Website Settings")
if ws and ws.get("app_logo"):
    logo = ws.get("app_logo")

if not logo:
    # Fallback to common field names across setups.
    navbar = safe_get("/api/resource/Navbar Settings/Navbar Settings")
    if navbar:
        logo = navbar.get("app_logo") or navbar.get("brand_image")

if not logo:
    logo = ""

fmt_url = f"{BASE}/api/resource/Print Format/{requests.utils.quote(FORMAT_NAME)}"
get_fmt = session.get(fmt_url, timeout=30)
get_fmt.raise_for_status()
fmt = get_fmt.json()["data"]
html = fmt.get("html", "")

old_block = '''<div class="inv-company">
      <strong>{{ doc.company or "Company" }}</strong><br>
      {{ doc.company_address_display or "Address line 1<br>Address line 2" }}
    </div>'''

new_block = f'''<div class="inv-company">
      {{% set comp_phone = frappe.db.get_value('Company', doc.company, 'phone_no') %}}
      {{% set comp_fax = frappe.db.get_value('Company', doc.company, 'fax') %}}
      {{% set comp_email = frappe.db.get_value('Company', doc.company, 'email') %}}
      <div style="display:flex; gap:12px; align-items:flex-start;">
        {'<img src="' + logo + '" alt="Logo" style="max-height:60px; max-width:140px; object-fit:contain;">' if logo else ''}
        <div>
          <strong style="font-size:16px;">Caravane Imports, Inc</strong><br>
          <div>{{{{ doc.company_address_display or "Address: -" }}}}</div>
          <div><strong>Phone:</strong> {{{{ comp_phone or "-" }}}} &nbsp; <strong>Fax:</strong> {{{{ comp_fax or "-" }}}}</div>
          <div><strong>Email:</strong> {{{{ comp_email or "-" }}}}</div>
        </div>
      </div>
    </div>'''

if old_block in html:
    html = html.replace(old_block, new_block)
else:
    # If previously modified, patch the company title only as safe fallback.
    html = html.replace("<strong>{{ doc.company or \"Company\" }}</strong>", "<strong style=\"font-size:16px;\">Caravane Imports, Inc</strong>")
    if "Phone:" not in html:
        html = html.replace(
            "{{ doc.company_address_display or \"Address line 1<br>Address line 2\" }}",
            "{{ doc.company_address_display or \"Address: -\" }}<br><strong>Phone:</strong> {{ frappe.db.get_value('Company', doc.company, 'phone_no') or '-' }} &nbsp; <strong>Fax:</strong> {{ frappe.db.get_value('Company', doc.company, 'fax') or '-' }}<br><strong>Email:</strong> {{ frappe.db.get_value('Company', doc.company, 'email') or '-' }}",
        )

put_fmt = session.put(fmt_url, json={"html": html}, timeout=30)
put_fmt.raise_for_status()

preview = session.get(
    f"{BASE}/printview",
    params={
        "doctype": "Sales Invoice",
        "name": INVOICE_NAME,
        "format": FORMAT_NAME,
        "no_letterhead": 0,
        "_lang": "en",
    },
    timeout=30,
)
preview.raise_for_status()
text = preview.text

print("Updated print format:", FORMAT_NAME)
print("Logo used:", logo or "(none found)")
print("Contains title:", "Caravane Imports, Inc" in text)
print("Contains Phone label:", "Phone:" in text)
print("Contains Fax label:", "Fax:" in text)
print("Contains Email label:", "Email:" in text)
print("Contains logo src:", (logo in text) if logo else False)
