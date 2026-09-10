import os
"""
Adds "Quick Add Item" to the Inventory Manager workspace:

  1. Client Script on Item list view — adds a "Quick Add Item" button
     that opens a dialog with the same fields as the inventory spreadsheet:
     Item Name, Brand, Item Group, Size, Items/Case, UPC, SKU, Cost

     Cost is written to Item.valuation_rate (no Custom Fields). A 0%-margin
     Pricing Rule ("Margin - <item_code>") and a matching Item Price
     (Standard Selling) are created alongside it, so the item is immediately
     wired into the same cost -> margin -> selling price model set up by
     scripts/inventory/setup_cost_margin_pricing.py.

  2. Updates the Inventory Manager workspace:
     - Shortcuts: Add Item (-> Item list), Items, Stock Entries, Item Price, Warehouses
     - Links: Items section, Stock section, Custom Reports section
"""

import requests
requests.packages.urllib3.disable_warnings()

URL  = "https://erpnext.karavanimports.com"
s = requests.Session(); s.verify = False
login_resp = s.post(f"{URL}/api/method/login",
                     data={"usr": os.environ.get("ERP_ADMIN_USR", "Administrator"),
                           "pwd": os.environ.get("ERP_ADMIN_PWD")}, timeout=15)
if login_resp.status_code != 200:
    raise SystemExit(f"Login failed {login_resp.status_code}: {login_resp.text[:300]}")
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
        return r.json().get("data", {})
    raise RuntimeError(f"{dt} upsert failed {r.status_code}: {r.text[:400]}")


# ── 1. Client Script on Item List ─────────────────────────────────────────────
print("=== [1] Client Script: Item list Quick Add button ===")

# Fetch item groups for the dropdown
ig_resp = s.get(f"{URL}/api/resource/Item Group",
                params={"fields": '["name"]', "limit": 100}, timeout=15)
item_groups = [g["name"] for g in ig_resp.json().get("data", [])
               if g["name"] != "All Item Groups"]
item_groups.sort()
# Build JS array literal
ig_js = "[" + ",".join(f'"{g}"' for g in item_groups) + "]"

# Company/currency needed to create a Pricing Rule (mirrors setup_cost_margin_pricing.py)
gd = s.get(f"{URL}/api/resource/Global Defaults/Global Defaults", timeout=15).json().get("data", {})
company = gd.get("default_company", "")
currency = s.get(f"{URL}/api/method/frappe.client.get_value",
                  params={"doctype": "System Settings", "fieldname": "currency"}, timeout=15) \
             .json().get("message", {}).get("currency") or "USD"

client_script = f"""
// Quick Add Item button on Item list view
frappe.listview_settings['Item'] = frappe.listview_settings['Item'] || {{}};

var _orig_onload = frappe.listview_settings['Item'].onload;
frappe.listview_settings['Item'].onload = function(listview) {{
    if (_orig_onload) _orig_onload(listview);

    listview.page.add_inner_button(__('Quick Add Item'), function() {{
        var item_groups = {ig_js};
        var options_html = item_groups.map(function(g) {{
            return '<option value="' + g + '">' + g + '</option>';
        }}).join('');

        var d = new frappe.ui.Dialog({{
            title: 'Quick Add Inventory Item',
            fields: [
                {{
                    label: 'Item Name / Description',
                    fieldname: 'item_name',
                    fieldtype: 'Data',
                    reqd: 1
                }},
                {{
                    label: 'Brand',
                    fieldname: 'brand',
                    fieldtype: 'Data'
                }},
                {{
                    label: 'Item Group / Category',
                    fieldname: 'item_group',
                    fieldtype: 'Select',
                    options: item_groups.join('\\n'),
                    reqd: 1
                }},
                {{
                    fieldtype: 'Column Break'
                }},
                {{
                    label: 'Size (e.g. 450 g, 1 LB)',
                    fieldname: 'package_size',
                    fieldtype: 'Data'
                }},
                {{
                    label: 'Items Per Case / Unit',
                    fieldname: 'items_per_case',
                    fieldtype: 'Data'
                }},
                {{
                    label: 'UPC / Barcode',
                    fieldname: 'custom_barcode',
                    fieldtype: 'Data'
                }},
                {{
                    label: 'SKU',
                    fieldname: 'custom_sku',
                    fieldtype: 'Data'
                }},
                {{
                    label: 'Cost (per unit)',
                    fieldname: 'cost',
                    fieldtype: 'Currency',
                    description: 'Selling price is derived from this via the item\\'s margin (0% by default \\u2014 adjust the "Margin - <item code>" Pricing Rule afterward).'
                }}
            ],
            primary_action_label: 'Save Item',
            primary_action: function(values) {{
                frappe.call({{
                    method: 'frappe.client.insert',
                    args: {{
                        doc: {{
                            doctype:       'Item',
                            item_name:     values.item_name,
                            brand:         values.brand || '',
                            item_group:    values.item_group || 'All Item Groups',
                            package_size:  values.package_size || '',
                            items_per_case: values.items_per_case || '',
                            custom_barcode: values.custom_barcode || '',
                            custom_sku:    values.custom_sku || '',
                            is_stock_item: 1,
                            stock_uom:     'Nos'
                        }}
                    }},
                    callback: function(r) {{
                        if (!r.message) return;
                        var item_code = r.message.name;
                        var cost = flt(values.cost) || 0;

                        frappe.show_alert({{
                            message: 'Item added: ' + r.message.item_name + ' (' + item_code + ')',
                            indicator: 'green'
                        }}, 5);
                        d.hide();
                        listview.refresh();

                        if (cost <= 0) return;

                        // New item has no stock yet, so there's no Bin to sync
                        // valuation_rate from -- set it directly.
                        frappe.call({{
                            method: 'frappe.client.set_value',
                            args: {{ doctype: 'Item', name: item_code, fieldname: 'valuation_rate', value: cost }}
                        }});

                        // 0% margin Pricing Rule, same as the bulk setup in
                        // setup_cost_margin_pricing.py -- selling price starts
                        // equal to cost until the margin is adjusted.
                        frappe.call({{
                            method: 'frappe.client.insert',
                            args: {{
                                doc: {{
                                    doctype: 'Pricing Rule',
                                    title: 'Margin - ' + item_code,
                                    apply_on: 'Item Code',
                                    items: [{{ item_code: item_code }}],
                                    selling: 1,
                                    price_or_product_discount: 'Price',
                                    margin_type: 'Percentage',
                                    margin_rate_or_amount: 0,
                                    rate_or_discount: 'Discount Percentage',
                                    discount_percentage: 0,
                                    company: '{company}',
                                    currency: '{currency}'
                                }}
                            }}
                        }});

                        frappe.call({{
                            method: 'frappe.client.insert',
                            args: {{
                                doc: {{
                                    doctype: 'Item Price',
                                    item_code: item_code,
                                    price_list: 'Standard Selling',
                                    selling: 1,
                                    price_list_rate: cost
                                }}
                            }}
                        }});
                    }},
                    error: function(r) {{
                        frappe.msgprint('Error saving item: ' + (r.message || r.exc || 'Unknown error'));
                    }}
                }});
            }}
        }});
        d.show();
    }});
}};
"""

upsert("Client Script", "Item-list-quick-add", {
    "doctype":    "Client Script",
    "name":       "Item-list-quick-add",
    "dt":         "Item",
    "view":       "List",
    "enabled":    1,
    "script":     client_script,
})


# ── 2. Update Inventory Manager workspace ─────────────────────────────────────
print("\n=== [2] Updating Inventory Manager workspace ===")

def sc(label, link_to, stype="DocType", color="#2490EF"):
    return {"doctype": "Workspace Shortcut", "label": label,
            "link_to": link_to, "type": stype, "color": color}

def lk(label, link_to):
    return {"doctype": "Workspace Link", "label": label,
            "link_to": link_to, "type": "Link", "hidden": 0, "onboard": 1}

def role_row(role):
    return {"doctype": "Workspace Role", "role": role}

upsert("Workspace", "Inventory Manager-Administrator", {
    "doctype": "Workspace",
    "name":    "Inventory Manager-Administrator",
    "label":   "Inventory Manager",
    "module":  "Stock",
    "is_hidden": 0,
    "roles": [
        role_row("Item Manager"),
        role_row("Stock Manager"),
        role_row("Stock User"),
    ],
    "shortcuts": [
        sc("Add Item",      "Item",        stype="DocType", color="#27ae60"),
        sc("Items",         "Item",        stype="DocType", color="#2490EF"),
        sc("Stock Entries", "Stock Entry", stype="DocType", color="#98a8d4"),
        sc("Item Price",    "Item Price",  stype="DocType", color="#2ecc71"),
        sc("Warehouses",    "Warehouse",   stype="DocType", color="#9b59b6"),
    ],
    "links": [
        # ── Items ─────────────────────────────────────────────────────────
        {"doctype": "Workspace Link", "label": "Items",
         "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Item",               "Item"),
        lk("Item Price",         "Item Price"),
        lk("Item Group",         "Item Group"),
        # ── Stock ─────────────────────────────────────────────────────────
        {"doctype": "Workspace Link", "label": "Stock",
         "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Stock Entry",        "Stock Entry"),
        lk("Stock Ledger Entry", "Stock Ledger Entry"),
        lk("Warehouse",          "Warehouse"),
        # ── Custom Reports ────────────────────────────────────────────────
        {"doctype": "Workspace Link", "label": "Custom Reports",
         "type": "Card Break", "link_to": "", "hidden": 0},
        lk("Item Price",         "Item Price"),
        lk("Stock Ledger Entry", "Stock Ledger Entry"),
    ],
    "charts": [],
})

print("""
=== Done ===

Client Script added to Item list view:
  -> Inventory Manager opens the Item list
  -> A "Quick Add Item" button appears in the top bar
  -> Clicking it opens a dialog with these fields:
       Item Name (required), Brand, Item Group (required),
       Size, Items Per Case, UPC/Barcode, SKU, Cost
  -> Item is saved immediately; if Cost is set, Item.valuation_rate,
     a 0%-margin Pricing Rule, and an Item Price (Standard Selling)
     are created so the item is live in the cost/margin/price model

Inventory Manager workspace:
  Shortcuts: Add Item, Items, Stock Entries, Item Price, Warehouses
  Sections : Items | Stock | Custom Reports
""")
