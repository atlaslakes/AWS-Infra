# Karavan Imports — System Architecture

## Overview

Karavan Imports runs on **ERPNext v15 (Frappe)** hosted on AWS, with **Base44** as the customer-facing portal. Base44 calls ERPNext's REST API for all data operations. Admin scripts in this repo manage data migration, price syncing, and inventory.

---

## Architecture Diagram

```
                         ┌──────────────────────────────────────────────┐
                         │                AWS Cloud (us-east-1)         │
                         │                                              │
  Customers ────────────>│  CloudFront (CDN / HTTPS / custom domain)    │
  Base44 Portal          │         │                                    │
                         │  EC2 i-0baea513db2b15557 (Docker Compose)    │
                         │  ┌────────────────────────────────────────┐  │
                         │  │  nginx  :8080  (frontend)              │  │
                         │  │  frappe backend  (ERPNext REST API)    │  │
                         │  │  websocket  (SocketIO)                 │  │
                         │  │  queue-long / queue-short (workers)    │  │
                         │  │  scheduler  (background tasks)         │  │
                         │  └────────────────────────────────────────┘  │
                         │         │                     │               │
                         │  RDS MariaDB          ElastiCache Redis       │
                         │  (primary DB)         (cache + queue)         │
                         │                                              │
                         │  S3  (file / attachment storage)             │
                         └──────────────────────────────────────────────┘
```

---

## Base44 ↔ ERPNext Integration

| Step | What Happens                                                                                       |
| ---- | -------------------------------------------------------------------------------------------------- |
| 1    | Customer submits application on Base44 portal                                                      |
| 2    | Base44 calls`POST /api/resource/Customer` on ERPNext with `approval_status = Pending`          |
| 3    | Staff reviews and approves/rejects in ERPNext                                                      |
| 4    | On approval, a Frappe Server Script fires → creates ERPNext User → sends login credentials email (from `accounts@karavanimports.com`) |
| 5    | Customer logs in to Base44 portal, authenticated against ERPNext                                   |

**Custom fields on Customer doctype:**

- `approval_status` — Pending / Approved / Rejected
- `approved_by` — which staff member approved

---

## ERPNext Site Details

| Setting          | Value                       |
| ---------------- | --------------------------- |
| Site             | `karavanimports.com`      |
| Company          | Atlas Lakes (abbr:`AL`)   |
| Warehouse        | `Stores - AL`             |
| Price List       | `Standard Selling`        |
| Admin user       | `Administrator`           |
| Docker container | `frappe_docker-backend-1` |

---

## Email Routing

Purpose-specific ERPNext **Email Account**s, all authenticating through one Google
OAuth token (`connected_user = karavanimports@atlaslakes.com`). Each has
`always_use_account_email_id_as_sender = 1` so `From` is forced to the account's
own address instead of falling back to `adminuser@atlaslakes.com`; on this
instance (Frappe **15.112.0**) `Reply-To` normally follows that forced sender —
`add_reply_to_header` / `reply_to_addresses` don't exist until a later v15.x.

That's not airtight, though: whatever caller composes mail can still pass an
explicit `reply_to` kwarg straight into `frappe.sendmail()`, bypassing the
Email Account entirely — confirmed live via a `[Contact Form] ...` message to
`support@karavanimports.com` that had `Reply-To: adminuser@atlaslakes.com`
baked into the queued MIME message. The caller isn't in this repo and isn't a
Server Script / Web Form / custom bench app on the box, so it can't be patched
at the source. [`scripts/setup/sanitize_reply_to.py`](scripts/setup/sanitize_reply_to.py)
closes the gap generically with a `Before Insert` Server Script on **Email
Queue**: whenever the resolved `From` is a real karavanimports.com address but
`Reply-To` still points at `*@atlaslakes.com`, it rewrites `Reply-To` to match
`From`. Legitimate internal mail actually sent from an atlaslakes.com address
(e.g. the old default `Karavan Imports` account) is left alone.

**Live on `erpnext.karavanimports.com`:**

| Account | Address | Direction | Used for |
| ------- | ------- | --------- | -------- |
| `Invoices - Karavan` | `invoice@karavanimports.com` | outgoing | invoice PDF to customer on Sales Invoice submit |
| `Accounts - Karavan` | `accounts@karavanimports.com` | outgoing | new-customer onboarding / credentials |
| `Support - Karavan` | `support@karavanimports.com` | outgoing (incoming **off**) | support replies |
| `Karavan Imports` | `adminuser@atlaslakes.com` | **default outgoing** + incoming | everything not explicitly routed |

**Notification** `Auto Send Sales Invoice to Customer` — Sales Invoice → Submit,
condition `doc.contact_email`, recipient `contact_email`, attaches print format
`Atlas Invoice Tracking Classic`, sender `Invoices - Karavan`. (Fixed by
[`scripts/setup/fix_live_email_routing.py`](scripts/setup/fix_live_email_routing.py) —
it had no recipients, print format, or sender.)

**Still manual (Google Workspace / human):**
- `default_outgoing` stays on `Karavan Imports` (adminuser@) — it's the only
  account proven to deliver. Move it to `Accounts - Karavan` only after
  confirming `accounts@karavanimports.com` is a verified "Send mail as" alias on
  `karavanimports@atlaslakes.com`.
- `Support - Karavan` incoming needs a Gmail filter `to:(support@karavanimports.com)`
  → label `ERPNext Support` before it can be turned on without ingesting the
  whole inbox as Issues.
- Stale `Accounting - Karavan` account (Basic auth, no stored password) — delete
  in the UI if unused.

[`scripts/setup/setup_email_routing.py`](scripts/setup/setup_email_routing.py)
describes an idealized clean-slate build (differently-named accounts, the old
catch-all disabled); the live site predates it, so
`fix_live_email_routing.py` is the reconcile-with-reality script.

---

## Item / Inventory Setup

Items are sourced from `aws-infra/Karavan Inventory-updated.xlsx` (323 products).

**Custom fields on Item doctype:**

| Field              | Type | Purpose                                     |
| ------------------ | ---- | ------------------------------------------- |
| `items_per_case` | Data | Units per case (for Price/Case calculation) |
| `package_size`   | Data | Size label (e.g. "400 g", "12 oz")          |

**Item Groups (categories):** ~79 groups on the live site (`Item Group` doctype, flat under `All Item Groups`) — this list has grown substantially from the original 13 and is the authoritative category source. Item code prefixes (below) no longer map cleanly 1:1 to a group — treat `item_group` as the source of truth for category, not the code prefix.

**Grocery / Pantry**
- APETIZER
- BAKING GOODS
- BREAD
- CAKE
- CANNED GOODS
- CANNED MEAT
- CHIPS
- CHOCALATE & CANDY
- COFFEE
- CONDIMENTS & SAUCES
- COOKIES & WAFFER
- DESSERT & SWEET
- DRY BEANS & LENTILS
- DRY FRUITS & DATES
- FLOUR
- GHEE
- GRAINS
- HALAWA & TAHINA
- HONEY & JAM
- JELLY
- JUICE
- LEMON JUICE & VINEGAR
- LENTILS
- Maamoul dates
- NUTS & SEEDS
- OIL
- OILS & GHEE
- OLIVE JAR
- OLIVE OIL
- PASTA & NOODLES
- PASTA & VERMICELLI
- PHILLY DOUGH & PASTRY
- PICKLES
- RAW NUTS
- RICE
- ROASTED SALTED NUTS
- SAUCES & PASTES
- SNACKS & SWEETS
- Soda
- SOUP
- SPICES
- STUFFED LEAVES
- SYRUP & ROSE WATER
- TEA & HERBS

**Fresh / Frozen**
- BACON GOODS
- DAIRY & CHEESE
- DAIRY NON REFRIG
- DAIRY REFRIG
- DELI CHEESE & OLIVES
- FRANKS & BACON
- FRESH BEEF
- FRESH CHICKEN
- FRESH FRUIT
- FRESH GOAT
- FRESH HERBS
- FRESH LAMB
- FRESH VEGETABLES
- FROZEN BEEF
- FROZEN CHICKEN
- FROZEN FISH
- FROZEN GOAT
- FROZEN KEBBAH & FALAFEL & KEBAB
- FROZEN LAMB
- FROZEN MEAT
- FROZEN PATTIES & SAMOSA
- FROZEN SEA FOOD
- FROZEN SWEET
- FROZEN VEGETABLES
- MILK & EGGS
- PARATHA & BREAD

**Other**
- BAKERY
- BEAUTY
- BEVERAGES
- CHARCOAL
- GENERAL
- HOUSEWHARE
- PANGEA BAKERY
- PANGEA MEAT
- PANGEA SPICES


---

## Inventory Manager Report

Query Report in ERPNext — `Inventory Manager` — shows:

| Column         | Source                                                           |
| -------------- | ---------------------------------------------------------------- |
| Item ID        | `tabItem.item_code`                                            |
| Description    | `tabItem.item_name`                                            |
| Brand          | `tabItem.brand`                                                |
| Category       | `tabItem.item_group`                                           |
| UPC / Barcode  | `tabItem Barcode` child table                                  |
| Items Per Case | `tabItem.items_per_case`                                       |
| Package Size   | `tabItem.package_size`                                         |
| Stock          | `SUM(tabBin.actual_qty)`, computed live — not a field on Item |
| Cost           | `tabItem.valuation_rate`                                       |
| Selling Price  | `tabItem Price` (Standard Selling)                             |
| Price/Case     | `price_list_rate × items_per_case`                            |

Stock is tracked natively (Bin / Stock Ledger Entry), wired via Item Lots — see `scripts/lots/_wire_lot_to_stock.py`. There's no `cases_on_hand` field on Item anymore (a Custom Field, previously used for this) — Custom Fields get serialized into every Item REST response, which wasn't wanted, and `Bin.actual_qty` was always the real source of truth it mirrored. The report just computes it live instead. Cost (`tabItem.valuation_rate`, a core field) is kept in sync with the stock ledger by a scheduled sync (see below) rather than a document-event hook — Bin never fires its own save hooks when updated by Sales Invoice/Stock Reconciliation/etc, and Stock Ledger Entry hooks proved unreliable around cancellations. Submitting a Sales Invoice with "Update Stock" checked (the default) deducts real stock immediately; cost/selling price catch up within a minute.

### Barcode images on invoices

Each Item stores a rendered barcode as a base64 PNG data-URI in
`custom_barcode_image`; the "Atlas Invoice Tracking Classic" print format just
`<img src>`s it (wkhtmltopdf can't run JS or import barcode libs at render time).

- **Generate/refresh:** [`scripts/inventory/regenerate_barcode_images.py`](scripts/inventory/regenerate_barcode_images.py)
  — the single source of truth. python-barcode PNGs with digits baked in and a
  full quiet zone: UPC-A (11/12 digits), EAN-13 (13), EAN-8 (8), ITF-14 (14),
  15/16-digit GS1 → stripped to 14. Anything else (non-numeric, other lengths,
  GS1-128 concat strings) → the image field is **cleared** so the print format
  falls back to plain text. Run it after any item/barcode import.
- The `Auto Barcode Image on Item Save` Server Script is now **normalization
  only** (pads 11→12 digits, sets `barcode_type` by length) — it no longer
  generates an image. It used to hand-roll SVG data-URIs, which wkhtmltopdf
  rendered as thin unscannable bars and which clobbered the good PNGs on every
  save. Reverted by [`scripts/inventory/slim_barcode_server_script.py`](scripts/inventory/slim_barcode_server_script.py).
- Superseded: `setup_barcode_images.py`, `_regen_barcode_images_with_text.py`,
  `set_barcode_type_upc.py` (the last blanket-set `barcode_type="UPC"`, which
  broke EAN-13/ITF-14 detection).
- A handful of items carry barcodes with an invalid check digit — ERPNext's own
  `Item.validate` rejects the save, so their image can't be updated until the
  barcode value is corrected against the supplier sheet.

---

## Expiry / Lot Tracking Fields

Custom DocType **Item Expiry Shipment** (`scripts/lots/karavan_expiry_tracking.py`) tracks per-shipment expiry, one record per received batch:

| Field             | Type                             | Purpose                                                |
| ----------------- | -------------------------------- | ------------------------------------------------------ |
| `item_code`     | Link (Item)                      | Which item this shipment/batch is for                  |
| `item_name`     | Data (fetched from`item_code`) | Display only                                           |
| `expiry_date`   | Date                             | Batch expiry date                                      |
| `status`        | Select                           | `Active` / `Expiring` / `Expired` / `Consumed` |
| `received_date` | Date                             | Defaults to today; when the batch arrived              |
| `qty`           | Float                            | Quantity received, in cases                            |
| `warehouse`     | Link (Warehouse)                 | Where the batch is stored                              |
| `reference`     | Data                             | Linked Stock Entry name                                |
| `notes`         | Small Text                       | Free-form notes                                        |

A matching custom field `expiry_date` (Date) is added to the **Stock Entry Detail** child table, so entering an expiry date on a Stock Entry row auto-creates/updates the corresponding Item Expiry Shipment record on submit.

---

## Pricing: Cost, Margin, Selling Price

Selling price is derived from cost via a per-item, customizable margin — all native ERPNext fields, no Custom Fields:

| Concept       | Field                                                                                                                          |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Cost          | `tabItem.valuation_rate`, weighted-average synced from `tabBin.valuation_rate`                                             |
| Margin        | One`Pricing Rule` per item (named `Margin - <item_code>`), `margin_type` (Percentage/Amount) + `margin_rate_or_amount` |
| Selling price | `tabItem Price` (Standard Selling), `price_list_rate` = cost × (1 + margin%) or cost + margin$                            |

Kept live by:

- **Sync Item Stock And Price - Scheduled** (`scripts/inventory/setup_stock_price_scheduled_sync.py`) — a Cron Server Script running every minute, recomputing cost and selling price from `Bin` for every item. Runs on a schedule rather than a document-event hook, since neither `Bin After Save` nor `Stock Ledger Entry After Insert` reliably fire/reflect current state for real ERPNext stock transactions (confirmed by testing).
- **Sync Item Price - Margin Change** (`Pricing Rule`, After Save, from `scripts/inventory/setup_cost_margin_pricing.py`) — margin edited → re-derive selling price from current cost immediately (this hook fires reliably since editing a Pricing Rule is a normal save).

All 391 items were seeded with a 0%-margin Pricing Rule (selling price = cost until adjusted per item). Cost was initially backfilled from the prior Toast POS / handwritten-scan prices (`update_prices.py`, `_push_scanned_prices.py`) — treated as the cost baseline, not the selling price, going forward. The old `custom_price` Custom Field and the `standard_rate` sync habit have been retired; adding items via the "Quick Add Item" button (`scripts/setup/setup_add_item_form.py`) now wires new items into this same model.

---

## ACH Payments Backend

New serverless stack (Lambda + API Gateway) for bidirectional ACH via **Dwolla + Plaid** — auto-collect from customers, auto-pay vendors. Separate from the EC2 Docker Compose stack since it's event-driven. See `docs/ACH-PAYMENTS-PLAN.md` for full design, `cloudformation/payments-backend.yaml` for infra, `payments/` for Lambda source, and `scripts/setup/setup_ach_payments.py` for the one-time ERPNext custom field / Mode of Payment setup.

### Sandbox smoke test

`scripts/setup/test_ach_sandbox.py` exercises the full rail against the Plaid + Dwolla **sandbox** using only the `.env` credentials — no deployed Lambdas, no Base44. It links two fake banks via Plaid, creates payer/payee Dwolla customers, verifies funding sources, and initiates collect / payout / refund transfers through the master funding source. `--recheck` re-polls the last run's transfers.

Known sandbox-account gaps (both are dashboard toggles, not code):

- **Plaid keys are not enabled for the Dwolla processor integration** (Plaid Dashboard → Developers → Integrations → Dwolla). Until enabled, `processor/token/create` returns `INVALID_PRODUCT`; the test script falls back to Dwolla's raw sandbox bank values + micro-deposit verification.
- **`POST /sandbox/simulations` returns 404** — the programmatic sandbox simulator is not enabled on this Dwolla sandbox account. Transfers initiate and sit `pending`; advance them from the Dwolla sandbox dashboard ("Sandbox" → "Process bank transfers"), then run `--recheck`.
- `setup_dwolla_master_account.py` creates the master funding source **`unverified`**; it must be verified (micro-deposits) before any transfer to/from it succeeds. The smoke test now verifies it automatically in sandbox.

### Money-correctness hardening (done)

Group 1 fixes applied to the Lambda handlers:

- **Idempotency.** `create_transfer()` takes an `idem_key`; `autopay-scan` derives a deterministic key per (invoice, due date, amount) or per installment row (`common/dwolla_client.py:idempotency_key`). A retried scan can no longer double-debit.
- **Re-entrancy.** `autopay-scan` skips any invoice/installment that already has a transfer id, treats a `null` `custom_ach_status` as due, skips `outstanding_amount <= 0`, persists after **each** installment transfer, and a single bad invoice no longer aborts the run (errors are collected and re-raised for the alarm).
- **Reconciliation actually builds a valid Payment Entry.** `dwolla-webhook` now calls ERPNext `get_payment_entry` server-side (party, bank accounts, company, allocation resolved there) then patches mode/`reference_no`/`reference_date` — the old hand-rolled doc was missing required fields and always failed on submit.
- **Webhook dedup + topic coverage.** Completion is idempotent (skips if a Payment Entry already references the transfer); topics are matched by suffix so `customer_transfer_*` / `customer_bank_transfer_*` variants are handled, not just bare `transfer_completed`.
- **Return codes.** The ACH return code is fetched from `GET {transfer}/failure` (it is not in the webhook payload), so R05/R07/R10/R11/R29/R51 are flagged `Returned` vs `Failed`.
- **TLS.** `ERPNextClient` no longer disables certificate verification.
- Both webhook handlers decode `isBase64Encoded` bodies before signature verification.

### Endpoint auth + bank-linking hardening (done — group 2)

- **`/link-token` and `/exchange-and-attach` now require a shared secret.** Base44 sends it as `X-Api-Key` (or `Authorization: Bearer …`); it lives in `PaymentsSecret.base44_shared_secret` (CFN param `Base44SharedSecret`). The handlers **fail closed** if the secret is unset, unless `ALLOW_UNAUTHENTICATED_CALLERS=true` is set on the function (sandbox only). See `common/auth.py`.
- **`exchange-and-attach` only marks a party `custom_bank_linked=1` once Dwolla reports the funding source `verified`** — otherwise it stores the IDs and returns `pending_verification`, so autopay-scan won't try to draw on an unverified account.
- Re-linking an already-attached bank (`DuplicateResource`) now **reuses the existing funding source** instead of 500ing / orphaning a second one.
- Missing `email` when a Dwolla Customer must be created returns a clean `400` (was an unhandled `KeyError`).

### Build + deploy pipeline (done — group 3)

- `payments/build.sh` builds the deploy zip (deps + handler packages at the root); must run on Linux x86_64 (CI does; Docker one-liner in the script header otherwise).
- `.github/workflows/deploy-payments.yml` builds, uploads to `s3://$LAMBDA_ARTIFACTS_BUCKET/payments/<env>/<sha>.zip`, and `cloudformation deploy`s `payments-<env>`. Triggers on push to `payments/**` / the template, or `workflow_dispatch` (dev/prod). Required GH secrets/vars are listed in `payments/README.md`.

### Dwolla webhook + master funding source (done — group 4)

- `scripts/setup/setup_dwolla_webhook.py` — creates the Dwolla webhook subscription pointing at the deployed API's `/webhooks/dwolla` (nothing created it before, so transfers would never reconcile), and un-pauses it (Dwolla pauses a subscription after ~200 delivery failures). `--list` / `--rotate` / `--delete`.
- `scripts/setup/verify_dwolla_master.py` — completes micro-deposit verification of the master funding source (`setup_dwolla_master_account.py` leaves it `unverified`, which blocks every transfer). Auto-completes in sandbox; `--init` then `--amounts A B` for production.

### NACHA authorization + secrets out of CloudFormation (done — group 5)

- **Customer debits require a retained authorization.** New Customer fields `custom_ach_authorization_{date,ip,text,reference}` (`setup_ach_payments.py`); Base44 writes them when the customer accepts autopay. `autopay-scan` skips any `collect` transfer for a customer without `custom_ach_authorization_date` (listed under the run's `skipped`, no alarm). Vendor payouts unaffected.
- **Credentials are no longer CloudFormation parameters.** They used to be passed as `NoEcho` params, which still left them retrievable via `describe-stacks` / change-set history. The template now creates `PaymentsSecret` as an empty container and never sets its value; `deploy-payments.yml` populates it out-of-band with `aws secretsmanager put-secret-value` after deploy. A redeploy can't clobber the value.

**Still procedural (business, not code):** Dwolla Business Verification (KYB) for Atlas Lakes before any production transfer; per-party KYC / Dwolla customer tier for invoices above the unverified send/receive caps; retaining the NACHA authorization text/records that Base44 now captures.

---

## GitHub Actions Workflows

18 workflows in `aws-infra/.github/workflows/` automate CRUD on ERPNext via REST API:

- Customer / Item / Invoice creation
- Deployment triggers
- SSM command dispatch

---

## Repo Structure

```
AWS/
├── aws-infra/
│   ├── cloudformation/          # VPC, EC2, RDS, ElastiCache, S3, CloudFront templates
│   ├── docker/                  # Docker Compose for ERPNext stack
│   ├── .github/workflows/       # 18 GitHub Actions
│   ├── configuration/           # 130+ SSM parameter JSON configs
│   └── Karavan Inventory-updated.xlsx   # Source of truth for items & stock
│
├── scripts/
│   ├── auth/                    # Role management and audit logging setup
│   ├── customers/                # Customer import/sync scripts
│   ├── diagnostics/              # One-off `_check_*` / `_fix_*` / `_diag_*` scripts (invoice PDF layout,
│   │                             #   pricing fixes, barcode regen, report/workspace repair, etc.)
│   ├── inventory/                # Stock/cost/price sync setup (scheduled sync, cost-margin pricing)
│   ├── invoices/                 # Invoice PDF format and deduction logic
│   ├── items/                    # Item import/export, autocode, renaming, price scripts
│   ├── lots/                     # Item Lot ↔ stock wiring, expiry tracking
│   ├── reports/                  # Query report setup (Inventory Manager, etc.)
│   ├── setup/                    # Initial ERPNext / ACH / add-item-form setup
│   └── ssm/                      # Generic + one-off SSM command runners
│
├── payments/                     # ACH payments Lambda source (Dwolla + Plaid)
├── cloudformation/               # ACH payments backend template
├── docs/                         # ACH-PAYMENTS-PLAN.md and other design docs
├── data/                         # Inventory exports, price review CSVs, source documents
│
├── .env.example                 # Required env vars (copy to .env and fill in)
└── README.md                    # This file
```

Scripts prefixed with `_` are one-off/diagnostic (not meant to be re-run generally); unprefixed scripts are reusable utilities.

---

## Infrastructure

Provisioned via CloudFormation:

| Resource    | Details                                        |
| ----------- | ---------------------------------------------- |
| EC2         | Single instance running Docker Compose         |
| RDS         | MariaDB (primary database)                     |
| ElastiCache | Redis × 2 (cache + queue)                     |
| S3          | File/attachment storage                        |
| CloudFront  | CDN + HTTPS termination                        |
| ACM         | SSL cert (DNS validated via GoDaddy)           |
| SSM         | Remote command execution into Docker container |

**Deploy:**

```bash
source .env && aws cloudformation deploy \
  --stack-name erpnext-${ENVIRONMENT} \
  --template-file aws-infra/cloudformation/erpnext.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    Environment=$ENVIRONMENT \
    KeyPairName=$KEY_PAIR_NAME \
    AllowedSSHCidr=$ALLOWED_SSH_CIDR \
    ERPNextVersion=$ERPNEXT_VERSION \
    DBPassword=$DB_PASSWORD \
    DBRootPassword=$DB_ROOT_PASSWORD \
    AdminPassword=$ADMIN_PASSWORD \
    EnableHTTPS=$ENABLE_HTTPS \
    DomainName=$DOMAIN_NAME \
    AlternateDomainName=$ALTERNATE_DOMAIN_NAME \
    NotificationEmail=$NOTIFICATION_EMAIL
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
ERP_ADMIN_PWD=your_admin_password_here
```

All admin scripts read credentials from `os.environ.get("ERP_ADMIN_PWD")`.

---

## Known Quirks

| Issue                                              | Workaround                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------------ |
| Frappe "format is an unsafe attribute"             | Certain item names blocked by sanitizer — use direct SQL INSERT via SSM |
| SSM payload limit 97 KB                            | Batch items ≤ 50 per SSM call                                           |
| `tabItem Barcode` empty via REST API             | Load barcodes via SSM SQL into`_barcodes.json` cache                   |
| UPC stored as float in Excel                       | Convert:`str(int(float(upc_raw)))`                                     |
| `tabWebsite Item` doesn't exist on this instance | Wrap each DELETE in try/except                                           |

---

*Last updated: 2026-09-04*
