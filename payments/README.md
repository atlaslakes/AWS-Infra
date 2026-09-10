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

## Building & deploying

`payments/build.sh [out.zip]` produces the deploy zip — dependencies + the
handler packages at the zip root (handler paths are `<pkg>.handler.handler`).
It installs deps for the running interpreter, so **run it on Linux x86_64**
(CI does). On macOS/Windows use the Docker one-liner in the script header.

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
| secret | `AWS_DEPLOY_ROLE_ARN`, `LAMBDA_ARTIFACTS_BUCKET`, `DWOLLA_KEY`, `DWOLLA_SECRET`, `DWOLLA_WEBHOOK_SECRET`, `DWOLLA_MASTER_FUNDING_SOURCE_URL`, `PLAID_CLIENT_ID`, `PLAID_SECRET`, `ERPNEXT_PAYMENTS_API_KEY`, `ERPNEXT_PAYMENTS_API_SECRET`, `BASE44_SHARED_SECRET`, `NOTIFICATION_EMAIL` |
| variable | `ERPNEXT_URL`, `DWOLLA_ENVIRONMENT`, `PLAID_ENVIRONMENT` |

Manual one-off:
```bash
bash payments/build.sh /tmp/p.zip
aws s3 cp /tmp/p.zip s3://$BUCKET/payments/dev/manual.zip
aws cloudformation deploy --template-file cloudformation/payments-backend.yaml \
  --stack-name payments-dev --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=dev CodeS3Bucket=$BUCKET CodeS3Key=payments/dev/manual.zip ...
```

## Data model this backend depends on

Created by `../scripts/setup/setup_ach_payments.py` — custom fields on Customer/Supplier (Dwolla IDs, bank-linked flag) and Sales/Purchase Invoice (`custom_autopay_enabled`, `custom_ach_transfer_id`, `custom_ach_status`, `custom_ach_installments`), the "ACH" Mode of Payment, and a restricted `payments-integration@karavanimports.com` API user.
