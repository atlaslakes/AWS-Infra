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

  4. Items table columns rebalanced: UPC widened (13% -> 22%) for a bigger,
     legible barcode; Item narrowed (40% -> 29%, it wraps naturally so the
     extra width wasn't needed); Qty widened slightly (5% -> 6%) so a
     4-digit qty never wraps to a second line; Code narrowed to 7% and
     de-emphasized (non-bold, smaller, !important so nothing else in the
     print stack can bold/color it) so it doesn't compete visually with the
     Item name next to it.

  5. Barcode image bumped up and, as of _regen_barcode_images_with_text.py,
     is generated with write_text=True so the human-readable digits are
     baked directly under the bars as part of the same PNG -- a normal
     UPC-A/EAN-13 label, rendered as one graphic. The print format no
     longer overlays a separate number span next to an image that already
     has one; the plain-text fallback only renders for items without a
     barcode image. Display size is locked to the image's real 1.922:1
     aspect ratio (30mm x 15.6mm) -- an earlier revision of this script set
     121x42 (2.88:1), which squished the image and made the baked-in digit
     strip at the bottom disappear for most items.

  6. Items table pagination: reverted to a single continuous <table> with
     no forced/manual row-count chunking. A prior revision carried over a
     "6 rows on page 1, 12 rows on every page after" hard chunk from an
     earlier script iteration (meant as a workaround for a wkhtmltopdf
     blank-gap pagination quirk), but it produced a second table with a
     duplicate header after a fixed 6 items regardless of how much room was
     actually left on the page -- wrong on both counts: it wasn't dynamic,
     and it wasn't even real pagination (no page break, just a second
     <table> element). Plain flowed content with <thead> repeating per
     page (standard print CSS) is simpler and correct; revisit only if the
     blank-gap quirk described in that old comment reappears in practice.

Usage:
  ERP_ADMIN_USER=... ERP_ADMIN_PWD=... python _fix_invoice_pdf_upc_qty_layout.py
  (run _regen_barcode_images_with_text.py first so the new image size/text
   is actually present on Item.custom_barcode_image before this pushes the
   template that expects it)
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
  .code { font-weight: 400 !important; font-size: 11px !important; color: #444 !important; }
  .desc { line-height: 1.35; white-space: normal; color: #000; font-weight: 500; }
  .desc .pkg-size { color: #000; font-size: 11px; font-weight: 400; }

  /* Scannable barcode image, in the UPC column. As of the barcode
     regeneration in _regen_barcode_images_with_text.py, the image itself
     is drawn with the human-readable UPC/EAN digits baked in under the
     bars (python-barcode's write_text) -- a normal UPC-A label look, one
     graphic -- so the print format no longer overlays a separate text
     element on top of/under it; that used to render as two disconnected
     pieces (bars, then an oddly offset number below). The plain-text
     fallback (.upc-text) only fires for items whose image hasn't been
     (re)generated yet, e.g. a barcode value that failed symbology
     detection. Width:height is fixed at 1.922:1 to match the actual
     generated PNG's aspect ratio (417x217px for both UPC-A and EAN-13,
     confirmed by direct generation) -- a mismatched ratio here silently
     squishes the image, and the baked-in digits (a thin strip at the
     bottom of the image) are what disappear first. Explicit width/height
     (not just max-width/max-height) so wkhtmltopdf can size the row up
     front instead of reflowing once the image loads -- that reflow was
     the main cause of pages breaking early and leaving a large blank gap
     under the table. */
  .upc-barcode { width: 30mm; height: 15.6mm; display: block; margin: 0 auto; }
  .upc-text { width: 30mm; text-align: center; white-space: nowrap; font-size: 11px; color: #000; margin: 0 auto; }

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

  <!-- Items, single continuous table -- no forced/manual page-break
       chunking. wkhtmltopdf paginates by slicing the flowed table content
       itself, repeating <thead> on each new page as normal print CSS
       behavior; row count per page is however many rows actually fit,
       not a fixed number. The table's border lives on the table itself
       (not a wrapping div), so it still renders as a fully closed box on
       every page: a border on an outer div isn't page-aware and would get
       cut off wherever the page break lands. -->
  {% set sorted_items = doc.items|sort(attribute='item_name', case_sensitive=False) %}
  <table class="items-tbl">
    <thead><tr><th class="r" style="width:6%">Qty</th><th style="width:7%">Code</th><th style="width:22%">UPC</th><th style="width:29%">Item</th><th class="r" style="width:12%">Price/Case</th><th class="r" style="width:12%">Price/Piece</th><th class="r" style="width:12%">Amount</th></tr></thead>
    <tbody>
      {% for it in sorted_items %}
      {% set pkg_size = frappe.db.get_value("Item", it.item_code, "package_size") or "" %}
      {% set ipc = (frappe.db.get_value("Item", it.item_code, "items_per_case") or 0) | float %}
      {% set std_price = (it.rate or 0) | float %}
      {% set price_per_case = std_price %}
      {% set price_per_piece = (std_price / ipc) if ipc > 0 else std_price %}
      {% set line_amt = price_per_case * (it.qty or 0) %}
      {% set bc_img = frappe.db.get_value("Item", it.item_code, "custom_barcode_image") %}
      <tr>
        <td class="r">{{ frappe.utils.fmt_money(it.qty, precision=0, currency="") }}</td>
        <td class="code">{{ it.item_code or "-" }}</td>
        <td style="padding-right:8px;">
          {% if bc_img %}
            <img src="{{ bc_img }}" class="upc-barcode" width="207" height="108">
          {% else %}
            <span class="upc-text">{{ it.barcode or "-" }}</span>
          {% endif %}
        </td>
        <td class="desc" style="padding-left:16px;">{{ it.item_name or "-" }}{% if pkg_size %} <span class="pkg-size">{% if ipc %}{{ ipc | int }} x {% endif %}{{ pkg_size }}</span>{% endif %}</td>
        <td class="r">{{ frappe.utils.fmt_money(price_per_case, currency=doc.currency) }}</td>
        <td class="r">{{ frappe.utils.fmt_money(price_per_piece, currency=doc.currency) }}</td>
        <td class="r">{{ frappe.utils.fmt_money(line_amt, currency=doc.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

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
