# ACH Payments Backend

Lambda source for the Dwolla + Plaid ACH payment backend. Full design rationale lives in `../docs/ACH-PAYMENTS-PLAN.md`; infrastructure (API Gateway, Lambdas, Secrets Manager, EventBridge) is defined in `../cloudformation/payments-backend.yaml`.

## Layout

```
payments/
├── requirements.txt          # dwollav2, plaid-python, requests, boto3 — packaged into the Lambda deploy zip
└── lambdas/
    ├── common/                # shared code, imported by every handler below
    │   ├── config.py          # loads Dwolla/Plaid/ERPNext credentials from Secrets Manager (PAYMENTS_SECRET_ARN)
    │   ├── erpnext_client.py  # thin REST wrapper (get/list/create/update/submit/cancel)
    │   ├── dwolla_client.py   # Dwolla customer/funding-source/transfer helpers
    │   └── plaid_client.py    # Plaid Link token + public token exchange + Dwolla processor token
    ├── link_token/            # POST /link-token — issues a Plaid Link token for Base44
    ├── exchange_and_attach/   # POST /exchange-and-attach — links a bank account to a Dwolla funding source
    ├── autopay_scan/          # EventBridge (hourly) — finds due autopay invoices/installments, initiates ACH transfers
    ├── dwolla_webhook/        # POST /webhooks/dwolla — reconciles transfer status into ERPNext Payment Entries
    └── plaid_webhook/         # POST /webhooks/plaid — flags stale bank links
```

Each Lambda directory is `handler.handler` (module `handler.py`, function `handler`), matching the CloudFormation `Handler` properties.

## Local development

Copy the `DWOLLA_*`/`PLAID_*`/`ERPNEXT_*` variables from the root `.env.example` into a local `.env`, install `requirements.txt` into a virtualenv, and invoke a handler directly, e.g.:

```bash
python -c "from lambdas.autopay_scan.handler import handler; print(handler({}, None))"
```

(This bypasses Secrets Manager — you'll need to stub `common.config.load_secrets()` or set `PAYMENTS_SECRET_ARN` and have AWS credentials available.)

## Deploying

There is no build pipeline yet. To deploy a change:
1. `pip install -r requirements.txt -t build/` then copy `lambdas/` into `build/`
2. Zip `build/` and upload to the `CodeS3Bucket`/`CodeS3Key` referenced by `cloudformation/payments-backend.yaml`
3. `aws cloudformation deploy --template-file cloudformation/payments-backend.yaml ...` (see parameters in the template)

## Data model this backend depends on

Created by `../scripts/setup/setup_ach_payments.py` — custom fields on Customer/Supplier (Dwolla IDs, bank-linked flag) and Sales/Purchase Invoice (`custom_autopay_enabled`, `custom_ach_transfer_id`, `custom_ach_status`, `custom_ach_installments`), the "ACH" Mode of Payment, and a restricted `payments-integration@karavanimports.com` API user.
