# Credit-card surcharge + Tap to Pay

Status (2026-11-23): backend built on branch `feat/card-surcharge-tap-to-pay`, not deployed.
Mobile app not started. Portal change pending (Base44 prompt below).

## Policy

| Payment | Fee |
|---|---|
| Credit card — Tap to Pay or portal Pay Now | **3%**, shown to the customer before they confirm |
| Debit / prepaid card | none (card-network + Durbin rules forbid it) |
| ACH / bank | none |
| Autopay (any method) | none — business decision, Nov 2026 |
| Customer billing state in `CardSurchargeExcludedStates` (default CT, MA) | none |

Enforced in `payments/lambdas/common/surcharge.py`. The rate is hard-capped at 3% in code.
The surcharge is booked in ERPNext as a negative row in the Payment Entry's standard
**Deductions or Loss** table → `Credit Card Surcharge Income` (no custom fields). The invoice
itself is only credited with the invoice amount.

## Before going live (owner checklist)

1. **Notify Stripe / card networks ≥ 30 days before** the first surcharged charge
   (Visa & Mastercard rule). Do it via Stripe support.
2. **Post the disclosure**: "A 3% surcharge applies to credit card payments. No surcharge for
   debit cards or bank (ACH) payments." — on the portal payment page, invoices, and a sticker
   / screen in the Tap to Pay app.
3. **Confirm state rules** for where you sell with your accountant/lawyer. Defaults exclude CT
   and MA. Colorado caps at 2% — add `CO` to the excluded list if you have Colorado customers
   (the code has one rate, not per-state rates).
4. Run `python scripts/setup/setup_card_surcharge.py` (dry run), then `--apply`, to create the
   income account.
5. Stripe Dashboard → Terminal → **Locations** → create one (Karavan warehouse address).
   Optionally pin it with the `TerminalLocationId` stack parameter.
6. **Apple**: request the *Tap to Pay on iPhone* entitlement in the Apple Developer account
   (takes ~weeks). Android needs nothing extra.
7. Give drivers/reps an ERPNext user with **Sales User** or **Accounts User**
   (`TerminalAllowedRoles`).

## API

All under the stack's `ApiBaseUrl`.

### Portal (Base44 shared secret, `X-Api-Key`)

| Route | Body | Returns |
|---|---|---|
| `POST /pay-now/quote` | `{invoice_doctype, invoice_name}` | `{base_cents, currency, payment_method_types, credit_card_surcharge_rate, publishable_key}` |
| `POST /pay-now/quote` | `+ confirmation_token` | `{base_cents, surcharge_cents, total_cents, surcharge_rate, funding, payment_method_type, card_brand, card_last4, currency}` |
| `POST /pay-now/confirm` | `{invoice_doctype, invoice_name, confirmation_token}` | breakdown + `{status, client_secret, payment_intent_id}`; `402` on decline; `409` if a payment is already in flight |
| `POST /pay-now` | legacy, **no surcharge** — turn off with `LegacyPayNow=disabled` once the portal is migrated |

### Tap to Pay app (ERPNext login, header `X-Frappe-Sid: <sid cookie from /api/method/login>`)

| Route | Body | Returns |
|---|---|---|
| `POST /terminal/connection-token` | `{}` | `{secret, location_id}` — use as the SDK token provider |
| `POST /terminal/payment-intent` | `{invoice_name}` | `{payment_intent_id, client_secret, base_cents, currency, customer_name}` |
| `POST /terminal/apply-surcharge` | `{payment_intent_id}` | `{base_cents, surcharge_cents, total_cents, funding, card_brand, card_last4}` |

App flow:
1. `discoverReaders({discoveryMethod: 'tapToPay'})` → `connectReader(..., locationId)`.
2. Driver picks an open invoice (read directly from ERPNext with the user's session).
3. `POST /terminal/payment-intent` → `retrievePaymentIntent(client_secret)`.
4. `collectPaymentMethod({paymentIntent, updatePaymentIntent: true})` — customer taps.
5. `POST /terminal/apply-surcharge` → show *Invoice $X + 3% credit card surcharge $Y = $Z*
   (or "no surcharge — debit card") and have the **customer** tap *Approve*.
6. Approve → `retrievePaymentIntent` again (amount changed) → `confirmPaymentIntent`.
   Decline → `cancelCollectPaymentMethod` / cancel the PaymentIntent.
7. The webhook posts the Payment Entry; the app can poll the invoice's `outstanding_amount`.

## Base44 prompt (portal Pay Now)

Paste into Base44:

> Update the invoice "Pay Now" flow to support a credit-card surcharge. Do not change how
> invoices are listed or anything else on the page.
>
> 1. When the customer opens Pay Now for an invoice, call our payments API
>    `POST {PAYMENTS_API_BASE}/pay-now/quote` with JSON `{"invoice_doctype": "Sales Invoice",
>    "invoice_name": <invoice name>}` and header `X-Api-Key: {PAYMENTS_SHARED_SECRET}` (server
>    side only — never expose the secret to the browser). Use the response's `publishable_key`,
>    `base_cents`, `currency` and `payment_method_types` to mount the Stripe Payment Element in
>    **deferred intent mode**: `stripe.elements({mode: 'payment', amount: base_cents, currency,
>    paymentMethodTypes: payment_method_types, paymentMethodCreation: 'manual'})`. Do NOT call
>    the old `/pay-now` endpoint any more.
> 2. Above the Payment Element show: "A 3% surcharge applies to credit card payments. No
>    surcharge for debit cards or bank (ACH) payments."
> 3. When the customer clicks **Review payment**: `elements.submit()`, then
>    `stripe.createConfirmationToken({elements, params: {return_url: <this page's URL>}})`. Send
>    the token id to `POST /pay-now/quote` with the same body plus `"confirmation_token"`.
> 4. Show a review box with the response: Invoice amount `base_cents`, Credit card surcharge
>    `surcharge_cents` (only if > 0, labelled "Credit card surcharge (3%)"), **Total**
>    `total_cents`, and the card brand + last4. If `surcharge_cents` is 0 and it's a card, say
>    "No surcharge (debit card)". Buttons: **Pay {total}** and **Change payment method**.
> 5. On **Pay**: `POST /pay-now/confirm` with the same body (including `confirmation_token`).
>    - `status` = `requires_action` → `await stripe.handleNextAction({clientSecret: client_secret})`.
>    - `succeeded` or `processing` → show "Payment received — your invoice will update shortly."
>    - HTTP 402 → show the `error` message and let them try another card.
>    - HTTP 409 → "A payment for this invoice is already in progress."
> 6. Amounts are in cents — divide by 100 for display. Never compute the surcharge in the
>    browser; always display what the API returns.
