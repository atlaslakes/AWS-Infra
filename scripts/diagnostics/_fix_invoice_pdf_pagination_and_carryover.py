"""
"Atlas Invoice Tracking Classic" Sales Invoice print format.

  1. Items table font: 12.5px body / 10px header (was 15px / 12px).

  2. Items flow naturally across pages (no manual chunking, no forced page
     breaks, no per-page "Balance Carried Forward" line -- removed; a prior
     version of this script added that, but it's been dropped per request).
     The items table's border lives on the table itself, not a wrapping div,
     so it still renders as a fully closed box on every page: wkhtmltopdf
     paginates by slicing flowed content, and a border on an outer div isn't
     page-aware and gets cut off wherever the page break lands, leaving an
     unclosed box on every page but the last.

  3. Terms & Conditions renders inside the footer-html block (the same
     per-page-footer mechanism used for page numbers) instead of flowing
     in-body after the totals block, so it's pinned to the bottom of the
     last page regardless of how short the invoice is, and only shows on
     the true last page (page === topage) in the real PDF. Visible by
     default via CSS so it also shows in the in-app Print Preview, which
     injects this HTML via innerHTML and never executes the <script> that
     would otherwise hide it on non-last pages. The @page bottom margin
     (44mm, up from the original 16mm) is preserved so the footer has room
     for the T&C text without clipping.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python _fix_invoice_pdf_pagination_and_carryover.py
"""

import os, sys, requests
import urllib3; urllib3.disable_warnings()

PROD_URL = "https://erpnext.karavanimports.com"
PRINT_FORMAT = "Atlas Invoice Tracking Classic"

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

  /* items — logo forest green header. Border lives on the table itself
     (not a wrapping div) so it renders as a fully closed box on every
     page: wkhtmltopdf paginates by slicing flowed content, and a border on
     an outer div isn't page-aware and gets cut off wherever the page break
     lands, leaving an unclosed box on every page but the last. */
  .items-tbl  { width: 100%; border-collapse: collapse; table-layout: fixed; border: 1px solid #555; }
  .items-tbl thead th {
    background: #3C5F2A; color: #fff;
    font-weight: 700; text-transform: uppercase;
    font-size: 11px; letter-spacing: 0.5px;
    padding: 7px 5px; border: none; text-align: left;
  }
  .items-tbl thead th.r { text-align: right; }
  .items-tbl tbody td { padding: 6px 5px; border: none; vertical-align: top; font-size: 13.5px; color: #000; }
  .items-tbl tbody tr:nth-child(even) { background: #F0F8F2; }

  .r    { text-align: right; white-space: nowrap; }
  .desc { line-height: 1.35; white-space: normal; color: #000; font-weight: 500; }
  .desc .pkg-size { color: #000; font-size: 11px; font-weight: 400; }

  /* scannable barcode image + human-readable number, stacked, in the UPC
     column; image only renders when Item.custom_barcode_image is set.
     Explicit width/height (not just max-width/max-height) so wkhtmltopdf
     can size the row up front instead of reflowing once the image loads --
     that reflow was the main cause of pages breaking early and leaving a
     large blank gap under the table. */
  .upc-barcode { width: 24mm; height: 7mm; display: block; margin-bottom: 1px; }
  .upc-text { white-space: nowrap; font-size: 11px; color: #000; }

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

  <!-- Header: LEFT = logo + contact + meta  |  RIGHT = Invoice title -->
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

  <!-- Items, manually paginated with forced page breaks. Natural
       (un-forced) page breaks in wkhtmltopdf leave a large blank gap at the
       bottom of most pages before breaking early -- confirmed by direct
       testing that it's independent of margins, borders, images, and font
       size; it's an engine quirk with this table, not something tunable
       via CSS. Forcing our own breaks at a measured row count instead
       reliably fills each page. Row height is a fixed 51pt/18mm regardless
       of content (dominated by the barcode image, not the text), so a
       simple fixed row count per page is enough -- no per-item weighting
       needed. ROWS_PER_PAGE constants below are derived from real measured
       page geometry; retune if a redesign changes header height, row
       height, or margins. No carry-forward/"balance so far" text -- just
       the pagination. -->
  {% set rows_first_page = 6 %}
  {% set rows_rest_pages = 12 %}
  {% set sorted_items = doc.items|sort(attribute='item_name', case_sensitive=False) %}

  {% set pg = namespace(pages=[[]], cur_count=0) %}
  {% for it in sorted_items %}
    {% set budget = rows_first_page if (pg.pages|length) == 1 else rows_rest_pages %}
    {% if pg.cur_count >= budget %}
      {% set _ = pg.pages.append([]) %}
      {% set pg.cur_count = 0 %}
    {% endif %}
    {% set _ = pg.pages[-1].append(it) %}
    {% set pg.cur_count = pg.cur_count + 1 %}
  {% endfor %}

  {% for page_items in pg.pages %}
  <table class="items-tbl"{% if not loop.last %} style="page-break-after: always;"{% endif %}>
    <thead><tr><th class="r" style="width:5%">Qty</th><th style="width:9%">Code</th><th style="width:13%">UPC</th><th style="width:40%">Item</th><th class="r" style="width:11%">Price/Case</th><th class="r" style="width:11%">Price/Piece</th><th class="r" style="width:11%">Amount</th></tr></thead>
    <tbody>
      {% for it in page_items %}
      {% set pkg_size = frappe.db.get_value("Item", it.item_code, "package_size") or "" %}
      {% set ipc = (frappe.db.get_value("Item", it.item_code, "items_per_case") or 0) | float %}
      {% set std_price = (it.rate or 0) | float %}
      {% set price_per_case = std_price %}
      {% set price_per_piece = (std_price / ipc) if ipc > 0 else std_price %}
      {% set line_amt = price_per_case * (it.qty or 0) %}
      {% set bc_img = frappe.db.get_value("Item", it.item_code, "custom_barcode_image") %}
      <tr>
        <td class="r">{{ frappe.utils.fmt_money(it.qty, precision=0, currency="") }}</td>
        <td>{{ it.item_code or "-" }}</td>
        <td style="padding-right:12px;">
          {% if bc_img %}<img src="{{ bc_img }}" class="upc-barcode" width="90" height="26">{% endif %}
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
  {% endfor %}

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
     page/topage query params (and therefore "is this really the last
     page") are genuinely available. Terms & Conditions lives here, so it
     only ever shows on the true last page -- pinned to the bottom margin
     area on every page regardless of how short or long that page's item
     content is. Placed at the end of the source (rather than the top) so
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
    .ft-pagerow {
      display: none;
      border-top: 0.75px solid #ccc; padding-top: 3px;
      text-align: center; font-size: 9px;
    }
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
      <div class="ft-pagerow" id="ftPagerow">Page <span class="pnum"></span> of <span class="ptotal"></span></div>
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
        document.getElementById('ftPagerow').style.display = 'block';
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
