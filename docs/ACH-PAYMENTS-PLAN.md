# ACH Payments Backend — Design

## Why

Karavan Imports has no way to move money electronically today — no payment gateway, no ACH, no bank-linking anywhere in the stack. Accounting is entirely manual (Payment Entries created by hand). This adds real ACH processing in both directions: auto-collect from customers on Sales Invoices, and auto-pay vendors on Purchase Invoices, using a bank-agnostic aggregator so any US bank works.

ERPNext ships with no payment gateway installed (confirmed: `docker/pwd-managed.yml` only installs the base `erpnext` app, not Frappe's separate `payments` app). Even Frappe's built-in `payments` app, had it been installed, only supports inbound checkout-style collection (Stripe/PayPal/Razorpay/Braintree/GoCardless) — none support outbound ACH payouts to vendors or a durable "link once, auto-pay recurring" flow. Hence a custom backend.

## Provider: Dwolla + Plaid

- **Dwolla** is the transfer engine — a bidirectional ACH network (debit-from and credit-to any US bank account) with first-class recurring transfer support.
- **Plaid** is the bank-linking layer — Dwolla's own recommended integration path (`processorToken`) for instant, bank-agnostic account verification without micro-deposits.
- Stripe ACH was ruled out: built around collecting from customers, fights the platform for arbitrary vendor payouts. GoCardless was ruled out: collections-only, weak on US outbound payouts.

## Where it runs

New, separate serverless stack (`cloudformation/payments-backend.yaml`) — API Gateway (HTTP API) + 5 Lambdas + an EventBridge-scheduled scan — rather than a new process on the existing single EC2 instance running the full Frappe stack. Keeps blast radius, IAM scope, and deploys independent of the ERPNext host.

## Data model (ERPNext custom fields)

| DocType | Field | Type | Purpose |
|---|---|---|---|
| Customer, Supplier | `custom_dwolla_customer_id` | Data | Dwolla Customer resource URL |
| Customer, Supplier | `custom_dwolla_funding_source_id` | Data | Verified funding source URL |
| Customer, Supplier | `custom_bank_linked` | Check | Set once linked; cleared if Plaid flags the link stale |
| Customer, Supplier | `custom_plaid_item_id` | Data | Routes Plaid webhooks back to the right party |
| Sales Invoice, Purchase Invoice | `custom_autopay_enabled` | Check | Opt-in flag Base44 sets |
| Sales Invoice, Purchase Invoice | `custom_ach_transfer_id` | Data | Dwolla transfer URL |
| Sales Invoice, Purchase Invoice | `custom_ach_status` | Select | Pending / Processing / Completed / Failed / Returned |

Plus a new "ACH" Mode of Payment. All created by `scripts/setup/setup_ach_payments.py`.

## Flow

1. **Bank linking**: Base44 calls `POST /link-token` to get a Plaid Link token, launches Plaid Link, then posts the result to `POST /exchange-and-attach`, which creates a Dwolla funding source and stores the IDs on the ERPNext Customer/Supplier record.
2. **Auto-pay scan**: `autopay-scan` runs hourly (EventBridge), finds due/unpaid invoices with `custom_autopay_enabled=1`, and initiates a Dwolla transfer (debit customer → Atlas Lakes, or Atlas Lakes → vendor). Sets `custom_ach_status=Processing`. No Payment Entry yet.
3. **Reconciliation**: `POST /webhooks/dwolla` verifies the HMAC signature and, on `transfer_completed`, creates + submits a Payment Entry (`mode_of_payment=ACH`) and sets `Completed`. On failure/return, sets `Failed`/`Returned`, cancels any Payment Entry, and a CloudWatch alarm notifies a human — retry policy for returns (e.g. R01 vs R10) is a business decision, not automated.
4. **Stale links**: `POST /webhooks/plaid` clears `custom_bank_linked` on `ITEM_LOGIN_REQUIRED`/`PENDING_EXPIRATION` so Base44 can prompt a re-link.

## What Base44 must add (outside this repo)

- "Link Bank Account" action calling `/link-token` → Plaid Link → `/exchange-and-attach`.
- "Auto-Pay" toggle setting `custom_autopay_enabled` directly via ERPNext REST (no new endpoint needed).
- Clear ACH authorization language + durable consent record at the point autopay is enabled (NACHA requirement).

## Compliance — procedural, must be handled by the business

- Dwolla Business Verification (KYB) for Atlas Lakes before any production transfers.
- Per-party KYC decision (unverified vs. verified Dwolla Customers), especially for vendor payouts.
- NACHA authorization retention for customer debits.
- Return code handling: R01 (NSF) vs R10 (unauthorized, never auto-retry) need different human follow-up.
- New Dwolla accounts often have lower transfer limits — pace rollout.
- Someone must own reconciling invoices stuck in Processing/Failed/Returned.

## Verification (sandbox, before any production key)

1. Dwolla + Plaid sandbox apps; populate `PaymentsSecret`.
2. Deploy `payments-backend.yaml` (dev).
3. Run `setup_ach_payments.py`; confirm custom fields exist.
4. Link a test Customer's bank via Plaid sandbox ("First Platypus Bank" / `user_good`/`pass_good`); confirm Dwolla funding source verified.
5. Create a due test Sales Invoice with autopay on; invoke `autopay-scan` manually; confirm `Processing`.
6. Confirm the Dwolla sandbox transfer completes and the webhook creates a submitted Payment Entry.
7. Repeat with a Dwolla sandbox R01 test case; confirm `Returned`, cancelled Payment Entry, alarm fires.
8. Repeat 4–6 for a test Supplier + Purchase Invoice (outbound direction).
9. Only then rotate to production keys; roll out with autopay off by default, per-relationship.
