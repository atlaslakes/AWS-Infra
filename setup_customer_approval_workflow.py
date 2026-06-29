import os
"""
When a Customer's Application Status is set to "Approved":
  1. A User account is created for the customer (if one doesn't exist)
  2. The user is assigned the "Customer" role profile
  3. An invitation email is sent so they can set their password and log in

Also adds custom_customer_email field to Customer so the email
can be captured when the application is submitted from base44.
"""

import requests, json, sys
requests.packages.urllib3.disable_warnings()

URL  = "https://www.karavanimports.com"
s = requests.Session(); s.verify = False
s.post(f"{URL}/api/method/login", data={"usr": "Administrator", "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
print("Logged in\n")

def q(n): return requests.utils.quote(str(n), safe="")

def exists(dt, name):
    return s.get(f"{URL}/api/resource/{q(dt)}/{q(name)}", timeout=10).status_code == 200

def upsert(dt, name, doc):
    if exists(dt, name):
        r = s.put(f"{URL}/api/resource/{q(dt)}/{q(name)}", json=doc, timeout=20)
        label = "updated"
    else:
        r = s.post(f"{URL}/api/resource/{q(dt)}", json=doc, timeout=20)
        label = "created"
    if r.status_code in (200, 201):
        print(f"  {label} : {dt} / {name}")
        return r.json()["data"]
    raise RuntimeError(f"{dt} upsert failed {r.status_code}: {r.text[:300]}")


# ── 1. Add customer_email field to Customer doctype ───────────────────────────
print("=== [1] Custom Field: customer_email ===")
upsert("Custom Field", "Customer-custom_customer_email", {
    "doctype": "Custom Field",
    "dt": "Customer",
    "label": "Customer Email",
    "fieldname": "custom_customer_email",
    "fieldtype": "Data",
    "options": "Email",
    "insert_after": "custom_application_section",
    "bold": 1,
    "in_list_view": 1,
    "description": "Email used to create the customer's login account on approval.",
})


# ── 2. Server Script — fires on Customer save ─────────────────────────────────
print("\n=== [2] Server Script ===")

script_code = """
prev = doc.get_doc_before_save()
was_approved = prev.custom_application_status == "Approved" if prev else False

if doc.custom_application_status == "Approved" and not was_approved:
    email = (doc.custom_customer_email or "").strip()
    if not email:
        frappe.msgprint("Customer approved but no Customer Email is set - no login created.", alert=True)
    elif frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
        user.reset_password(send_email=True)
        frappe.msgprint("Password reset email sent to " + email, alert=True)
    else:
        parts = (doc.customer_name or email).split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "role_profile_name": "Customer",
            "user_type": "System User",
            "send_welcome_email": 1,
        })
        user.insert(ignore_permissions=True)
        frappe.msgprint("User account created and welcome email sent to " + email, alert=True)
"""

upsert("Server Script", "Customer Approval - Create User", {
    "doctype": "Server Script",
    "name": "Customer Approval - Create User",
    "script_type": "DocType Event",
    "dt": "Customer",
    "doctype_event": "After Save",
    "enabled": 1,
    "script": script_code,
})

print("""
=== Done ===

Added to Customer form:
  "Customer Email" field (below Application Status) — fill this in
  when the customer submits their application from base44.

Server Script active on Customer → After Save:
  When Application Status is changed to "Approved":
    - Creates a User with the Customer role profile
    - Sends a welcome email with a password setup link
    - Shows a confirmation alert in ERPNext

If the user already exists, a password reset email is sent instead.
""")
