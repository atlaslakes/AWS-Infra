# ERPNext Server Script (DocType Event)
# Reference Doctype: Item
# Event: Before Save
# Purpose: block duplicate-looking items and enforce custom alias uniqueness.

import re


def _normalize(value):
    if not value:
        return ""
    # lowercase + collapse spaces + keep alnum/spaces only for near-duplicate detection
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^a-z0-9 ]", "", value)
    return value


normalized_name = _normalize(doc.item_name)
if not normalized_name:
    frappe.throw("Item Name is required.")

# Check near-duplicate names (case/space/punctuation-insensitive)
for row in frappe.get_all(
    "Item",
    filters={"name": ["!=", doc.name]},
    fields=["name", "item_name"],
    limit=5000,
):
    if _normalize(row.item_name) == normalized_name:
        frappe.throw(
            "A similar item already exists: {0} ({1}). "
            "Use the existing item or rename this one clearly.".format(row.item_name, row.name)
        )

# Optional alias uniqueness check if custom_invoice_alias exists in your Item doctype
if doc.get("custom_invoice_alias"):
    existing = frappe.db.exists(
        "Item",
        {
            "name": ["!=", doc.name],
            "custom_invoice_alias": doc.custom_invoice_alias,
        },
    )
    if existing:
        frappe.throw(
            "Invoice Alias '{0}' is already used by Item {1}."
            .format(doc.custom_invoice_alias, existing)
        )
