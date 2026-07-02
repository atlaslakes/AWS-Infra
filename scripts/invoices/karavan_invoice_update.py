import os
import requests

requests.packages.urllib3.disable_warnings()

INSTANCES = [
    "https://www.karavanimports.com",   # production
    "http://3.216.86.193",              # staging / test
]
PASS = os.environ.get("ERP_ADMIN_PWD")

def make_session(url):
    s = requests.Session(); s.verify = False
    s.post(f"{url}/api/method/login", data={"usr": "Administrator", "pwd": PASS})
    return s

s = make_session(INSTANCES[0])  # keep s for any legacy inline calls

NEW_HTML = """\
<style>
  @page { size: A4 portrait; margin: 10mm 9mm 54mm 9mm; }
  .inv {
    font-family: "Calibri", "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #1f1f1f; font-size: 11.5px; line-height: 1.5;
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
  .co-name { font-size: 17px; font-weight: 700; margin-bottom: 2px; color: #1f1f1f; }
  .co-sub  { color: #555; font-size: 10px; line-height: 1.7; }

  /* meta box — left, under company */
  .meta-box { width: 100%; border-collapse: collapse; border: 1.5px solid #444; margin-top: 10px; }
  .meta-box td { border: none; padding: 0 7px; font-size: 10.5px; white-space: nowrap; line-height: 1.6; }
  .meta-box .lbl { font-weight: 700; background: #F3F8F4; width: 68px;
                   text-align: right; color: #3C5F2A; }
  .meta-box .val { font-weight: 600; }

  /* Invoice title — right column */
  .inv-title {
    font-size: 72px; font-weight: 900; color: #111;
    line-height: 0.9; letter-spacing: -2px; margin-bottom: 10px;
  }

  /* T&C at bottom */
  .btm-terms { font-size: 8.5px; color: #555; line-height: 1.5; }
  .btm-terms p { margin: 0 0 4px 0; }
  .btm-terms b { color: #3C5F2A; }

  /* address */
  .addr-cap {
    display: block; font-weight: 700; color: #C87A1A;
    text-transform: uppercase; font-size: 9px; letter-spacing: 1.3px;
    border-bottom: 1.5px solid #C87A1A; padding-bottom: 2px; margin-bottom: 6px;
  }
  .addr-body { font-size: 11px; line-height: 1.35; min-height: 0; }
  .addr-body p, .addr-body br+br { margin: 0; padding: 0; display: block; }
  .addr-body p { margin: 0 !important; padding: 0 !important; }

  /* info strip */
  .info-strip {
    background: #F3F8F4; border-left: 3px solid #C87A1A;
    padding: 5px 10px; font-size: 10px; color: #666; margin-bottom: 12px;
  }
  .info-strip table { border-collapse: collapse; width: 100%; table-layout: fixed; }
  .info-strip td    { border: none; padding: 0 8px 0 0; }

  /* items — logo forest green header */
  .items-wrap { border: 1px solid #555; }
  .items-tbl  { width: 100%; border-collapse: collapse; table-layout: fixed; }
  .items-tbl thead th {
    background: #3C5F2A; color: #fff;
    font-weight: 700; text-transform: uppercase;
    font-size: 9px; letter-spacing: 0.5px;
    padding: 7px 5px; border: none; text-align: left;
  }
  .items-tbl thead th.r { text-align: right; }
  .items-tbl tbody td { padding: 5px 5px; border: none; vertical-align: top; font-size: 11px; }
  .items-tbl tbody tr:nth-child(even) { background: #F0F8F2; }

  .r    { text-align: right; }
  .desc { line-height: 1.25; white-space: normal; }

  /* weight */
  .weight-line {
    font-size: 12px; font-weight: 700; border-top: 1px solid #ddd;
    padding: 7px 5px 4px; color: #3C5F2A;
  }
  .weight-line span { font-weight: 400; font-size: 11px; color: #555; margin-left: 18px; }

  /* totals — right-aligned */
  .totals-wrap { width: 38%; margin-left: auto; margin-top: 10px; }
  .totals-tbl  { width: 100%; border-collapse: collapse; }
  .totals-tbl td { padding: 3.5px 6px; border: none; font-size: 11px; }
  .totals-tbl .sep td { border-top: 1px solid #ddd; }
  .totals-tbl .grand td {
    font-weight: 700; font-size: 12.5px;
    border-top: 2px solid #3C5F2A; padding-top: 6px; color: #3C5F2A;
  }

  /* T&C pinned to page bottom */
  .btm-terms {
    position: fixed; bottom: 12mm; left: 0; right: 0;
    font-size: 8px; color: #555; line-height: 1.4;
    background: white; border-top: 1.5px solid #3C5F2A; padding-top: 6px;
  }
  .btm-terms .tc-label { font-weight: 700; color: #3C5F2A; font-size: 8.5px;
                         text-transform: uppercase; letter-spacing: 1px; margin-bottom: 3px; }
  .btm-terms p { margin: 0 0 3px 0; }
  .btm-terms b { color: #3C5F2A; }

  /* footer */
  .inv-footer {
    position: fixed; bottom: 4mm; width: 100%;
    text-align: center; font-size: 9.5px; color: #999;
    font-family: "Calibri", Arial, sans-serif;
  }
  .page, .topage { display: inline; }
</style>

<script>
(function(){
  var v={};
  window.location.search.substring(1).split('&').forEach(function(p){
    var kv=p.split('='); v[decodeURIComponent(kv[0])]=decodeURIComponent(kv[1]||'');
  });
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('.page').forEach(function(e){ if(v.page) e.textContent=v.page; });
    document.querySelectorAll('.topage').forEach(function(e){ if(v.topage) e.textContent=v.topage; });
  });
})();
</script>

{% set logo = frappe.db.get_value("Website Settings", "Website Settings", "app_logo") %}
{% set inv_num = doc.name.split('-')[-1] | int %}
{% set wt_kg = doc.total_net_weight or 0 %}
{% set wt_lb = wt_kg * 2.20462 %}

<div class="inv-footer">Page <span class="page"></span> of <span class="topage"></span></div>

<div class="inv">
  <div class="accent-bar"></div>

  <!-- Header: LEFT = logo + contact + meta  |  RIGHT = Invoice title + T&C -->
  <table style="width:100%; border-collapse:collapse; margin-bottom:14px; table-layout:fixed;">
    <colgroup><col style="width:46%;"><col style="width:54%;"></colgroup>
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
            <tr><td class="lbl">Page</td><td class="val">Page <span class="page"></span> of <span class="topage"></span></td></tr>
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
    <colgroup><col style="width:50%;"><col style="width:50%;"></colgroup>
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

  <!-- Items -->
  <div class="items-wrap">
    <table class="items-tbl">
      <colgroup>
        <col style="width:7%;"><col style="width:9%;"><col style="width:11%;">
        <col style="width:33%;"><col style="width:12%;"><col style="width:13%;"><col style="width:15%;">
      </colgroup>
      <thead><tr>
        <th class="r">Qty</th><th>Code</th><th>UPC</th><th>Item</th>
        <th class="r">Price/Case</th><th class="r">Price/Piece</th><th class="r">Amount</th>
      </tr></thead>
      <tbody>
        {% set ns = namespace(sub=0.0) %}
        {% for it in doc.items %}
        {% set pkg_size = frappe.db.get_value("Item", it.item_code, "package_size") or "" %}
        {% set ipc = (frappe.db.get_value("Item", it.item_code, "items_per_case") or 0) | float %}
        {% set std_price = (frappe.db.get_value("Item Price", {"item_code": it.item_code, "price_list": "Standard Selling"}, "price_list_rate") or 0) | float %}
        {% set price_per_case = std_price * ipc if ipc > 0 else std_price %}
        {% set line_amt = (it.qty | float) * price_per_case %}
        {% set ns.sub = ns.sub + line_amt %}
        <tr>
          <td class="r">{{ frappe.utils.fmt_money(it.qty, precision=0, currency="") }}</td>
          <td>{{ it.item_code or "-" }}</td>
          <td style="padding-right:10px;">{{ it.barcode or "-" }}</td>
          <td class="desc" style="padding-left:14px;">{{ it.item_name or "-" }}{% if pkg_size %} <span style="color:#888; font-size:10px;">{% if ipc %}{{ ipc | int }} x {% endif %}{{ pkg_size }}</span>{% endif %}</td>
          <td class="r">{{ frappe.utils.fmt_money(price_per_case, currency=doc.currency) }}</td>
          <td class="r">{{ frappe.utils.fmt_money(std_price, currency=doc.currency) }}</td>
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
  {% set grand = ns.sub - disc + taxes %}
  <div class="totals-wrap">
    <table class="totals-tbl">
      <tbody>
        <tr><td>Subtotal</td><td class="r">{{ frappe.utils.fmt_money(ns.sub, currency=doc.currency) }}</td></tr>
        {% if disc > 0 %}
        <tr class="sep"><td>Discount</td><td class="r">-{{ frappe.utils.fmt_money(disc, currency=doc.currency) }}</td></tr>
        {% endif %}
        {% if taxes > 0 %}
        <tr class="sep"><td>Tax</td><td class="r">{{ frappe.utils.fmt_money(taxes, currency=doc.currency) }}</td></tr>
        {% endif %}
        <tr class="grand"><td>Grand Total</td><td class="r">{{ frappe.utils.fmt_money(grand, currency=doc.currency) }}</td></tr>
      </tbody>
    </table>
  </div>

  <!-- T&C fixed to page bottom -->
  <div class="btm-terms">
    <div class="tc-label">Terms &amp; Conditions</div>
    {% if doc.terms %}
      {{ doc.terms | safe }}
    {% else %}
      <p>All deliveries must be checked by the customer at the time of delivery. If you receive an item that is damaged or defective, report it to your driver immediately and contact us at accounting@karavanimports.com.</p>
      <p>All missing, defective or damaged products and returns <b>MUST BE REPORTED WITHIN 3 DAYS</b> from the date of delivery. Items not reported within the 72-hour period are ineligible for credit. Returns after 72 hours are subject to a <b>30% restocking fee</b>. Frozen or short-dated items are not eligible for return unless deemed defective at the sole discretion of Karavan Imports.</p>
      <p><b>Please do not deduct payments from invoice.</b> All credits will appear on subsequent invoices.</p>
    {% endif %}
  </div>

</div>
"""

for url in INSTANCES:
    sess = make_session(url)
    r = sess.put(
        f"{url}/api/resource/Print%20Format/Atlas%20Invoice%20Tracking%20Classic",
        json={"html": NEW_HTML},
        timeout=30,
    )
    label = "PROD" if "karavanimports" in url else "STAGING"
    print(f"[{label}] {r.status_code} modified:", r.json().get("data", {}).get("modified", ""))
    if r.status_code != 200:
        print(r.text[:200])
