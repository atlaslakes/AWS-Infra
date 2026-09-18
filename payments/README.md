# Stripe Payments Backend

Lambda source for the Stripe payments backend (cards + ACH). Infrastructure (API Gateway, Lambdas, Secrets Manager, EventBridge) is defined in `../cloudformation/payments-backend.yaml`.

## Layout

```
payments/
├── requirements.txt          # stripe, requests, boto3 — packaged into the Lambda deploy zip
└── lambdas/
    ├── common/                # shared code, imported by every handler below
    │   ├── config.py          # loads Stripe/ERPNext credentials from Secrets Manager (PAYMENTS_SECRET_ARN)
    │   ├── erpnext_client.py  # thin REST wrapper (get/list/create/update/submit/cancel)
    │   └── stripe_client.py   # Stripe customer/setup-intent/payment-intent/webhook helpers
    ├── setup_intent/           # POST /setup-intent — issues a SetupIntent for Base44 to confirm with Stripe.js
    ├── attach_payment_method/  # POST /attach-payment-method — writes the confirmed PaymentMethod back onto the ERPNext party
    ├── pay_now/                # POST /pay-now — on-demand one-time payment against an invoice
    ├── autopay_scan/           # EventBridge (hourly) — finds due autopay invoices/installments, initiates off-session charges
    └── stripe_webhook/         # POST /webhooks/stripe — reconciles payment status into ERPNext Payment Entries
```

Each Lambda directory is `handler.handler` (module `handler.py`, function `handler`), matching the CloudFormation `Handler` properties.

## Payment flows

- **Setup (save a payment method)**: Base44 calls `/setup-intent` → gets a `client_secret` → drives Stripe.js/Elements (Payment Element, setup mode) directly with the customer, so raw card/bank details never hit our Lambdas → on success, calls `/attach-payment-method` with the `setup_intent_id`, which re-fetches the SetupIntent server-side (never trusts the client), reads the resulting PaymentMethod (and Mandate, for bank), and writes the IDs onto the ERPNext Customer/Supplier.
- **Pay Now (one-time, on demand)**: Base44 calls `/pay-now` with an invoice — no saved payment method required. Returns a PaymentIntent `client_secret` for the customer to confirm with a card or bank account right then. The invoice's payment status is only ever updated by the webhook once Stripe confirms the charge, not by this endpoint.
- **Auto-pay (recurring, off-session)**: the hourly `autopay-scan` Lambda scans ERPNext for invoices with `custom_autopay_enabled=1` that are due, and — for customers with a saved, verified payment method — creates an off-session `PaymentIntent` charged against the saved `custom_stripe_payment_method_id`. Bank auto-pay requires an active mandate + `custom_ach_authorization_date` on file (NACHA); cards don't.
- **Reconciliation**: `stripe_webhook` is the single endpoint for all Stripe events (`payment_intent.succeeded`/`payment_intent.payment_failed`/`mandate.updated`/etc.), verified via `Stripe-Signature`. On success it builds+submits a Payment Entry via ERPNext's `get_payment_entry` whitelisted method, idempotent on `Payment Entry.reference_no == payment_intent.id`.

## Local development

Copy the `STRIPE_*`/`ERPNEXT_*` variables from the root `.env.example` into a local `.env`, install `requirements.txt` into a virtualenv, and invoke a handler directly, e.g.:

```bash
python -c "from lambdas.autopay_scan.handler import handler; print(handler({}, None))"
```

(This bypasses Secrets Manager — you'll need to stub `common.config.load_secrets()` or set `PAYMENTS_SECRET_ARN` and have AWS credentials available.)

Use the [Stripe CLI](https://stripe.com/docs/stripe-cli) to forward webhook events to a local endpoint during development: `stripe listen --forward-to <local-url>/webhooks/stripe` (gives you a local `whsec_...` for `STRIPE_WEBHOOK_SECRET`).

## Building & deploying

`payments/build.sh [out.zip]` produces the deploy zip — dependencies + the
handler packages at the zip root (handler paths are `<pkg>.handler.handler`).
It installs deps for the running interpreter. Stripe's SDK is pure Python (no
compiled extensions), so unlike the old Dwolla/Plaid version this most likely
no longer strictly requires building on Linux x86_64 — but this hasn't been
re-verified, so the script still recommends it; use the Docker one-liner in
the script header on macOS/Windows if in doubt.

CI: `.github/workflows/deploy-payments.yml` runs on push to `payments/**` or
`cloudformation/payments-backend.yaml` (and via `workflow_dispatch` with a
`dev`/`prod` choice). It builds the zip, uploads it to
`s3://$LAMBDA_ARTIFACTS_BUCKET/payments/<env>/<sha>.zip`,
`aws cloudformation deploy`s the stack, then **populates `PaymentsSecret`
out-of-band** with `aws secretsmanager put-secret-value` (built from the GitHub
secrets/vars below with `jq`). `CodeS3Key` is keyed on the commit SHA, so every
run redeploys the function code.

The credentials are **not** CloudFormation parameters (they used to be, which
left them readable via `describe-stacks` / change-set history). The template
creates `PaymentsSecret` as an empty container and never sets its value, so a
redeploy can't clobber it. On the very first deploy of a fresh stack the
functions exist for a few seconds with an empty secret before the
`put-secret-value` step runs — nothing calls them in that window. Rotating the
secret only takes effect on the next Lambda cold start (`common/config`
caches per execution environment).

Required GitHub config for the workflow:

| Kind | Name |
|---|---|
| secret | `AWS_DEPLOY_ROLE_ARN`, `LAMBDA_ARTIFACTS_BUCKET`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `ERPNEXT_PAYMENTS_API_KEY`, `ERPNEXT_PAYMENTS_API_SECRET`, `BASE44_SHARED_SECRET`, `NOTIFICATION_EMAIL` |
| variable | `ERPNEXT_URL` |

Use Stripe **test-mode** keys (`sk_test_`/`pk_test_`/a test-mode `whsec_`) for `payments-dev`; live keys are reserved for `payments-prod`.

Manual one-off:
```bash
bash payments/build.sh /tmp/p.zip
aws s3 cp /tmp/p.zip s3://$BUCKET/payments/dev/manual.zip
aws cloudformation deploy --template-file cloudformation/payments-backend.yaml \
  --stack-name payments-dev --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=dev CodeS3Bucket=$BUCKET CodeS3Key=payments/dev/manual.zip ...
```

## Data model this backend depends on

Created by `../scripts/setup/setup_stripe_payments.py` — custom fields on Customer/Supplier (Stripe customer/payment-method/mandate IDs, payment-method-type, bank-linked/card-on-file flags, NACHA authorization record) and Sales/Purchase Invoice (`custom_autopay_enabled`, `custom_stripe_payment_intent_id`, `custom_payment_status`, `custom_ach_installments`), the "ACH" and "Card" Modes of Payment, and a restricted `payments-integration@karavanimports.com` API user (the deployed stack currently still uses the broad admin API key as a stopgap — a pre-existing gap, not introduced by the Stripe migration).

## Known gap: vendor payouts

The old Dwolla version also auto-paid **Purchase Invoices** (vendor payouts) by transferring from Atlas Lakes' own Dwolla funding source to the vendor's linked bank account — both modeled as funding sources under one Dwolla account. Stripe has no equivalent primitive for paying an arbitrary external bank account from your own balance without **Stripe Connect** (Custom/Express connected accounts), which is materially more setup (KYC/onboarding per vendor) and was out of scope for this migration. `autopay_scan` currently only processes `collect` (customer-charge) invoices — Purchase Invoice auto-pay is not implemented in the Stripe version. Vendor payments need to be entered manually in ERPNext until Stripe Connect (or another payout mechanism) is scoped.
