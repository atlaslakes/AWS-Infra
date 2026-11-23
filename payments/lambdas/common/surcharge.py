"""Credit-card surcharge rules, shared by Pay Now (portal) and Tap to Pay.

Policy (see docs/CARD-SURCHARGE-TAP-TO-PAY.md for the compliance background):
  * Only CREDIT cards are surcharged. Debit and prepaid cards are never
    surcharged (Durbin / card-network rules), and neither is an "unknown"
    funding type — when in doubt, don't charge the fee.
  * ACH / bank payments are never surcharged.
  * Only Sales Invoices (customers paying us) are surcharged.
  * The rate is capped at 3% (card-network maximum) no matter what the
    CARD_SURCHARGE_RATE env var says — a misconfiguration fails loudly
    instead of over-charging.
  * Customers whose billing state is in CARD_SURCHARGE_EXCLUDED_STATES
    (default CT, MA) are not surcharged.

Autopay is deliberately NOT surcharged (business decision, Nov 2026); this
module is simply never called from autopay_scan.
"""

import os
from decimal import Decimal, ROUND_HALF_UP

MAX_RATE = Decimal("0.03")
_DEFAULT_RATE = "0.03"
_DEFAULT_EXCLUDED_STATES = "CT,MA"

_US_STATES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL",
    "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "PUERTO RICO": "PR", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}


def surcharge_rate():
    rate = Decimal(os.environ.get("CARD_SURCHARGE_RATE", _DEFAULT_RATE))
    if rate < 0 or rate > MAX_RATE:
        raise ValueError(f"CARD_SURCHARGE_RATE={rate} is outside the allowed 0..{MAX_RATE}")
    return rate


def normalize_state(state):
    s = (state or "").strip().upper()
    return _US_STATES.get(s, s)


def excluded_states():
    raw = os.environ.get("CARD_SURCHARGE_EXCLUDED_STATES", _DEFAULT_EXCLUDED_STATES)
    return {normalize_state(s) for s in raw.split(",") if s.strip()}


def compute(base_cents, *, funding, invoice_doctype, billing_state=None):
    """Returns the full breakdown for a payment of base_cents (the invoice
    amount being paid). funding is Stripe's card funding type ("credit",
    "debit", "prepaid", "unknown") or None for non-card methods."""
    base_cents = int(base_cents)
    state = normalize_state(billing_state)
    eligible = (
        invoice_doctype == "Sales Invoice"
        and funding == "credit"
        and state not in excluded_states()
    )
    rate = surcharge_rate() if eligible else Decimal("0")
    surcharge_cents = int((Decimal(base_cents) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "base_cents": base_cents,
        "surcharge_cents": surcharge_cents,
        "total_cents": base_cents + surcharge_cents,
        "surcharge_rate": str(rate),
        "funding": funding,
    }


def describe(invoice_name, breakdown):
    """Statement/receipt description. Stripe receipts show the PaymentIntent
    description, which is how the surcharge appears as its own disclosed
    amount on the customer's receipt."""
    base = breakdown["base_cents"] / 100
    fee = breakdown["surcharge_cents"] / 100
    if not breakdown["surcharge_cents"]:
        return f"Karavan Imports invoice {invoice_name}"
    pct = (Decimal(breakdown["surcharge_rate"]) * 100).normalize()
    return (
        f"Karavan Imports invoice {invoice_name}: ${base:,.2f} "
        f"+ {pct}% credit card surcharge ${fee:,.2f}"
    )


def billing_state_for(erp, invoice):
    """Best-effort lookup of the customer's billing state from the invoice's
    linked Address. None when there is no address on the invoice."""
    address_name = invoice.get("customer_address")
    if not address_name:
        return None
    address = erp.get("Address", address_name)
    return (address or {}).get("state")
