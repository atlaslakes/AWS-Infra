"""
Minimal, targeted fix for "Atlas Invoice Tracking Classic - By Category":
only moves Terms & Conditions into the real per-page footer (so it's pinned
to the bottom and only ever shows on the true last page), same mechanism
just applied to "Atlas Invoice Tracking Classic" in
_fix_invoice_pdf_pagination_and_carryover.py.

Deliberately does NOT touch anything else in this format -- font sizes,
category grouping, and the existing (less accurate, full-grand-total)
"Total Carried Forward" footer line are all left exactly as they are.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python _fix_invoice_pdf_by_category_tc_footer.py
"""

import os, sys, requests
import urllib3; urllib3.disable_warnings()

PROD_URL = "https://erpnext.karavanimports.com"
PRINT_FORMAT = "Atlas Invoice Tracking Classic - By Category"

HTML = r"""<style>
  @page { size: A4 portrait; margin: 10mm 9mm 44mm 9mm; }
  .inv {
    font-family: "Calibri", "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #000; font-size: 13.5px; line-height: 1.5;
  }

  /* logo-accurate greens + amber */
  /* Forest green ray: #3C5F2A  |  Amber ray: #C87A1A  |  Olive: #8A9B38 */
  .accent-bar {
    height: 5px;
    background: linear-gradient(90deg,
      #E0C090 0%, #C87A1A 18%, #8A9B38 34%,
      #3C5F2A 50%, #6B3020 68%, #8B2513 84%, #C87A1A 100%);
    margin-bottom: 14px;
  }

  /* company info */
  .logo    { max-height: 50px; max-width: 105px; vertical-align: top; margin-right: 9px; }
  .co-info { display: inline-block; vertical-align: top; }
  .co-name { font-size: 18px; font-weight: 700; margin-bottom: 2px; color: #000; }
  .co-sub  { color: #333; font-size: 11.5px; line-height: 1.7; }

  /* meta box — left, under company */
  .meta-box { width: 100%; border-collapse: collapse; border: 1.5px solid #444; margin-top: 10px; }
  .meta-box td { border: none; padding: 0 7px; font-size: 12px; white-space: nowrap; line-height: 1.6; }
  .meta-box .lbl { font-weight: 700; background: #F3F8F4; width: 68px;
                   text-align: right; color: #3C5F2A; }
  .meta-box .val { font-weight: 600; }

  /* Invoice title — right column */
  .inv-title {
    font-size: 72px; font-weight: 900; color: #111;
    line-height: 0.9; letter-spacing: -2px; margin-bottom: 10px;
  }

  /* address */
  .addr-cap {
    display: block; font-weight: 700; color: #C87A1A;
    text-transform: uppercase; font-size: 9px; letter-spacing: 1.3px;
    border-bottom: 1.5px solid #C87A1A; padding-bottom: 2px; margin-bottom: 6px;
  }
  .addr-body { font-size: 12.5px; color: #000; line-height: 1.35; min-height: 0; }
  .addr-body p, .addr-body br+br { margin: 0; padding: 0; display: block; }
  .addr-body p { margin: 0 !important; padding: 0 !important; }

  /* info strip */
  .info-strip {
    background: #F3F8F4; border-left: 3px solid #C87A1A;
    padding: 5px 10px; font-size: 11.5px; color: #333; margin-bottom: 12px;
  }
  .info-strip table { border-collapse: collapse; width: 100%; table-layout: fixed; }
  .info-strip td    { border: none; padding: 0 8px 0 0; }

  /* items — logo forest green header */
  .items-wrap { border: 1px solid #555; }
  .items-tbl  { width: 100%; border-collapse: collapse; table-layout: fixed; }
  .items-tbl thead th {
    background: #3C5F2A; color: #fff;
    font-weight: 700; text-transform: uppercase;
    font-size: 12px; letter-spacing: 0.5px;
    padding: 8px 5px; border: none; text-align: left;
  }
  .items-tbl thead th.r { text-align: right; }
  .items-tbl tbody td { padding: 7px 5px; border: none; vertical-align: top; font-size: 15px; color: #000; }
  .items-tbl tbody tr:nth-child(even) { background: #F0F8F2; }

  .r    { text-align: right; }
  .desc { line-height: 1.35; white-space: normal; color: #000; font-weight: 500; }
  .desc .pkg-size { color: #000; font-size: 13px; font-weight: 400; }

  /* category group header row inside the items table */
  .cat-row td {
    background: #E4EEE6 !important; color: #3C5F2A; font-weight: 700;
    text-transform: uppercase; font-size: 11.5px; letter-spacing: 0.5px;
    padding: 5px 6px; border-top: 1px solid #3C5F2A; border-bottom: 1px solid #3C5F2A;
  }

  /* scannable barcode image + human-readable number, stacked, in the UPC
     column; image only renders when Item.custom_barcode_image is set */
  .upc-barcode { max-width: 100%; max-height: 9mm; display: block; margin-bottom: 1px; }
  .upc-text { white-space: nowrap; font-size: 12px; color: #000; }

  /* weight */
  .weight-line {
    font-size: 13px; font-weight: 700; border-top: 1px solid #ddd;
    padding: 7px 5px 4px; color: #3C5F2A;
  }
  .weight-line span { font-weight: 400; font-size: 12px; color: #333; margin-left: 18px; }

  /* totals — right-aligned */
  .totals-wrap { width: 38%; margin-left: auto; margin-top: 10px; }
  .totals-tbl  { width: 100%; border-collapse: collapse; }
  .totals-tbl td { padding: 3.5px 6px; border: none; font-size: 12.5px; color: #000; }
  .totals-tbl .sep td { border-top: 1px solid #ddd; }
  .totals-tbl .grand td {
    font-weight: 700; font-size: 14px;
    border-top: 2px solid #3C5F2A; padding-top: 6px; color: #3C5F2A;
  }
</style>

{% set logo = frappe.db.get_value("Website Settings", "Website Settings", "app_logo") %}
{% set inv_num = doc.name.split('-')[-1] | int %}
{% set wt_kg = doc.total_net_weight or 0 %}
{% set wt_lb = wt_kg * 2.20462 %}

<div class="inv">
  <div class="accent-bar"></div>

  <!-- Header: LEFT = logo + contact + meta  |  RIGHT = Invoice title + T&C -->
  <table style="width:100%; border-collapse:collapse; margin-bottom:14px; table-layout:fixed;">

    <tbody><tr>
      <td style="vertical-align:top; padding-right:18px;">
        {% if logo %}<img src="{{ logo }}" class="logo">{% endif %}<span class="co-info">
          <div class="co-name">Karavan Imports, Inc</div>
          <div class="co-sub">
            8035 Ranchers Rd. NE, Fridley, MN 55432<br>
            accounting@karavanimports.com
          </div>
        </span>
        <table class="meta-box">
          <tbody>
            <tr><td class="lbl">Invoice</td><td class="val">{{ inv_num }}</td></tr>
            <tr><td class="lbl">Customer</td><td class="val">{{ doc.customer_name or doc.customer }}</td></tr>
            <tr><td class="lbl">Date</td><td class="val">{{ frappe.utils.formatdate(doc.posting_date) }}</td></tr>
            <tr><td class="lbl">Order</td><td class="val">{{ inv_num }}</td></tr>
          </tbody>
        </table>
      </td>
      <td style="vertical-align:top;">
        <div class="inv-title">Invoice</div>
        <div class="info-strip" style="margin-bottom:0;">
          <table><tbody>
            <tr><td><b>PO:</b> {{ doc.po_no or "-" }}</td><td><b>Ship Via:</b> {{ doc.shipping_rule or "-" }}</td></tr>
            <tr><td><b>Terms:</b> {{ doc.tc_name or "-" }}</td><td><b>Rep:</b> {{ doc.contact_display or "-" }}</td></tr>
          </tbody></table>
        </div>
      </td>
    </tr></tbody>
  </table>

  <!-- Bill To / Ship To -->
  <table style="width:100%; border-collapse:collapse; margin-bottom:14px; table-layout:fixed;">

    <tbody><tr>
      <td style="vertical-align:top; padding-right:20px;">
        <span class="addr-cap">Bill To</span>
        <div class="addr-body">{{ doc.address_display or doc.customer_address or "No billing address" }}</div>
      </td>
      <td style="vertical-align:top;">
        <span class="addr-cap">Ship To</span>
        <div class="addr-body">{{ doc.shipping_address or doc.shipping_address_name or doc.address_display or "No shipping address" }}</div>
      </td>
    </tr></tbody>
  </table>

  <!-- Items, grouped by Category (Item Group) then alphabetically within each group -->
  <div class="items-wrap">
    <table class="items-tbl">

      <thead><tr><th class="r" style="width:5%">Qty</th><th style="width:9%">Code</th><th style="width:20%">UPC</th><th style="width:33%">Item</th><th class="r" style="width:11%">Price/Case</th><th class="r" style="width:11%">Price/Piece</th><th class="r" style="width:11%">Amount</th></tr></thead>
      <tbody>
        {% set sorted_items = [] %}
        {% for it in doc.items %}
          {% set grp = frappe.db.get_value("Item", it.item_code, "item_group") or "" %}
          {% set _ = sorted_items.append((grp, (it.item_name or "").lower(), it)) %}
        {% endfor %}
        {% set ns = namespace(last_grp=None) %}
        {% for grp, nm, it in sorted_items|sort %}
        {% set pkg_size = frappe.db.get_value("Item", it.item_code, "package_size") or "" %}
        {% set ipc = (frappe.db.get_value("Item", it.item_code, "items_per_case") or 0) | float %}
        {% set std_price = (it.rate or 0) | float %}
        {% set price_per_case = std_price %}
        {% set price_per_piece = (std_price / ipc) if ipc > 0 else std_price %}
        {% set line_amt = price_per_case * (it.qty or 0) %}
        {% set bc_img = frappe.db.get_value("Item", it.item_code, "custom_barcode_image") %}
        {% if grp != ns.last_grp %}
        <tr class="cat-row"><td colspan="7">{{ grp or "Uncategorized" }}</td></tr>
        {% set ns.last_grp = grp %}
        {% endif %}
        <tr>
          <td class="r">{{ frappe.utils.fmt_money(it.qty, precision=0, currency="") }}</td>
          <td>{{ it.item_code or "-" }}</td>
          <td style="padding-right:12px;">
            {% if bc_img %}<img src="{{ bc_img }}" class="upc-barcode">{% endif %}
            <span class="upc-text">{{ it.barcode or "-" }}</span>
          </td>
          <td class="desc" style="padding-left:16px;">{{ it.item_name or "-" }}{% if pkg_size %} <span class="pkg-size">{% if ipc %}{{ ipc | int }} x {% endif %}{{ pkg_size }}</span>{% endif %}</td>
          <td class="r">{{ frappe.utils.fmt_money(price_per_case, currency=doc.currency) }}</td>
          <td class="r">{{ frappe.utils.fmt_money(price_per_piece, currency=doc.currency) }}</td>
          <td class="r">{{ frappe.utils.fmt_money(line_amt, currency=doc.currency) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  {% if wt_kg > 0 %}
  <div class="weight-line">
    Total Weight <span>{{ "%.2f"|format(wt_kg) }} KG &nbsp;/&nbsp; {{ "%.2f"|format(wt_lb) }} LB</span>
  </div>
  {% endif %}

  <!-- Totals right-aligned -->
  {% set disc  = (doc.discount_amount or 0) | float %}
  {% set taxes = (doc.total_taxes_and_charges or 0) | float %}
  <div class="totals-wrap">
    <table class="totals-tbl">
      <tbody>
        <tr><td>Subtotal</td><td class="r">{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</td></tr>
        {% if disc > 0 %}
        <tr class="sep"><td>Discount</td><td class="r">-{{ frappe.utils.fmt_money(disc, currency=doc.currency) }}</td></tr>
        {% endif %}
        {% if taxes > 0 %}
        <tr class="sep"><td>Tax</td><td class="r">{{ frappe.utils.fmt_money(taxes, currency=doc.currency) }}</td></tr>
        {% endif %}
        <tr class="grand"><td>Grand Total</td><td class="r">{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</td></tr>
      </tbody>
    </table>
  </div>

</div>

<!-- Real per-page footer. Frappe extracts this by id (regardless of where
     it sits in the document) and renders it once per PDF page via
     wkhtmltopdf's own --footer-html pass, which is the only place
     page/topage query params are genuinely available. Terms & Conditions
     lives here instead of flowing in-body after the totals block, so it's
     pinned to the bottom of the last page regardless of how short the
     invoice is. Placed at the end of the source (rather than the top) so
     that contexts which don't do the id-based extraction -- e.g. the
     in-app Print Preview -- render it after the invoice body instead of
     before it. -->
<div id="footer-html">
  <style>
    .ft-wrap {
      font-family: "Calibri", "Helvetica Neue", Helvetica, Arial, sans-serif;
      color: #666; width: 100%;
      position: relative; height: 40mm;
    }
    .ft-bottom {
      position: absolute; bottom: 0; left: 0; right: 0;
    }
    .ft-tc {
      border-top: 1.5px solid #3C5F2A; padding-top: 6px; margin-bottom: 6px;
      font-size: 8px; color: #555; line-height: 1.4;
    }
    .ft-tc .tc-label {
      font-weight: 700; color: #3C5F2A; font-size: 8.5px;
      text-transform: uppercase; letter-spacing: 1px; margin-bottom: 3px;
    }
    .ft-tc p { margin: 0 0 3px 0; }
    .ft-tc b { color: #3C5F2A; }
    .ft-row  { display: none; width: 100%; border-top: 0.75px solid #ccc; padding-top: 3px; }
    .ft-row.ft-shown { display: table; }
    .ft-cell { display: table-cell; vertical-align: middle; width: 33.33%; font-size: 9px; }
    .ft-page { text-align: center; }
    .ft-carry { text-align: right; font-weight: 700; color: #3C5F2A; }
  </style>
  <div class="ft-wrap">
    <div class="ft-bottom">
      <div class="ft-tc" id="ftTc">
        <div class="tc-label">Terms &amp; Conditions</div>
        {% if doc.terms %}
          {{ doc.terms | safe }}
        {% else %}
          <p>All deliveries must be checked by the customer at the time of delivery. If you receive an item that is damaged or defective, report it to your driver immediately and contact us at accounting@karavanimports.com.</p>
          <p>All missing, defective or damaged products and returns <b>MUST BE REPORTED WITHIN 3 DAYS</b> from the date of delivery. Items not reported within the 72-hour period are ineligible for credit. Returns after 72 hours are subject to a <b>30% restocking fee</b>. Frozen or short-dated items are not eligible for return unless deemed defective at the sole discretion of Karavan Imports.</p>
          <p><b>Please do not deduct payments from invoice.</b> All credits will appear on subsequent invoices.</p>
        {% endif %}
      </div>
      <div class="ft-row" id="ftPagerow">
        <div class="ft-cell"></div>
        <div class="ft-cell ft-page">Page <span class="pnum"></span> of <span class="ptotal"></span></div>
        <div class="ft-cell ft-carry"><span class="carry-total"></span></div>
      </div>
    </div>
  </div>
  <script>
  (function(){
    var v = {};
    window.location.search.substring(1).split('&').forEach(function(p){
      var kv = p.split('=');
      v[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || '');
    });
    document.addEventListener('DOMContentLoaded', function(){
      var page = parseInt(v.page, 10), topage = parseInt(v.topage, 10);
      // Only real wkhtmltopdf pages actually get page/topage query params,
      // so only reveal the row (and fill it in) there. Left hidden
      // elsewhere (e.g. Print Preview) instead of showing a broken-looking
      // static "Page  of " with no numbers in it.
      if (page && topage) {
        document.querySelector('.pnum').textContent = v.page;
        document.querySelector('.ptotal').textContent = v.topage;
        document.getElementById('ftPagerow').classList.add('ft-shown');
      }
      if (page && topage && page < topage) {
        document.querySelector('.carry-total').textContent =
          'Total Carried Forward: {{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}';
      }
      // T&C is visible by default (CSS), which is what non-paginated
      // contexts need -- e.g. the in-app Print Preview, which injects this
      // HTML via innerHTML, so this <script> never even runs there. Only
      // the real wkhtmltopdf PDF pass (where scripts do run) explicitly
      // hides it on pages before the true last page.
      if (page && topage && page < topage) {
        document.getElementById('ftTc').style.display = 'none';
      }
    });
  })();
  </script>
</div>
"""

if __name__ == "__main__":
    user = os.environ.get("ERP_ADMIN_USER") or os.environ.get("ERP_ADMIN_USR", "Administrator")
    pwd = os.environ.get("ERP_ADMIN_PWD")
    if not pwd:
        sys.exit("Set ERP_ADMIN_PWD (and optionally ERP_ADMIN_USER) before running.")

    s = requests.Session()
    s.verify = False
    r = s.post(f"{PROD_URL}/api/method/login", data={"usr": user, "pwd": pwd}, timeout=15)
    if r.status_code != 200:
        sys.exit(f"Login failed: {r.status_code} {r.text[:200]}")

    resp = s.put(
        f"{PROD_URL}/api/resource/Print Format/{PRINT_FORMAT}",
        json={"doctype": "Print Format", "name": PRINT_FORMAT, "html": HTML},
        timeout=30,
    )
    print("Updated:", resp.status_code, "OK" if resp.status_code in (200, 201) else resp.text[:400])
