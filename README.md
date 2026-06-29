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

| Step | What Happens |
|------|-------------|
| 1 | Customer submits application on Base44 portal |
| 2 | Base44 calls `POST /api/resource/Customer` on ERPNext with `approval_status = Pending` |
| 3 | Staff reviews and approves/rejects in ERPNext |
| 4 | On approval, a Frappe Server Script fires → creates ERPNext User → sends login credentials email |
| 5 | Customer logs in to Base44 portal, authenticated against ERPNext |

**Custom fields on Customer doctype:**
- `approval_status` — Pending / Approved / Rejected
- `approved_by` — which staff member approved

---

## ERPNext Site Details

| Setting | Value |
|---------|-------|
| Site | `karavanimports.com` |
| Company | Atlas Lakes (abbr: `AL`) |
| Warehouse | `Stores - AL` |
| Price List | `Standard Selling` |
| Admin user | `Administrator` |
| Docker container | `frappe_docker-backend-1` |

---

## Item / Inventory Setup

Items are sourced from `aws-infra/Karavan Inventory-updated.xlsx` (323 products).

**Custom fields on Item doctype:**
| Field | Type | Purpose |
|-------|------|---------|
| `cases_on_hand` | Int | Stock quantity (set via UPC matching from Excel) |
| `items_per_case` | Data | Units per case (for Price/Case calculation) |
| `package_size` | Data | Size label (e.g. "400 g", "12 oz") |

**Item code prefix map:**

| Prefix | Category |
|--------|----------|
| BEAN | Beans / Lentils / Rice |
| GRAIN | Grains |
| OIL | Oils |
| BEV | Beverages |
| SNACK | Snacks / Chips |
| NUT | Nuts / Dried Fruit |
| DAIRY | Dairy |
| SPICE | Spices |
| PICKLE | Pickles |
| PASTA | Pasta |
| COND | Condiments |
| CHAR | Charcoal |
| GEN | General |

---

## Inventory Manager Report

Query Report in ERPNext — `Inventory Manager` — shows:

| Column | Source |
|--------|--------|
| Item ID | `tabItem.item_code` |
| Description | `tabItem.item_name` |
| Brand | `tabItem.brand` |
| Category | `tabItem.item_group` |
| UPC / Barcode | `tabItem Barcode` child table |
| Items Per Case | `tabItem.items_per_case` |
| Package Size | `tabItem.package_size` |
| Cases On Hand | `tabItem.cases_on_hand` |
| Price/Item | `tabItem Price` (Standard Selling) |
| Price/Case | `price_list_rate × items_per_case` |

**Invoice deduction:** On Sales Invoice submit, a Server Script deducts invoice qty from `cases_on_hand`. On cancel, it restores.

---

## Pricing

Prices come from **Toast POS export** (`Data_06_23.csv`, 18 k rows).

Matching logic in `update_prices.py`:
1. **UPC match** — all normalized variants (strip leading zeros, drop last 2 digits, last 11/12 digits)
2. **Fuzzy fallback** — Brand containment + description similarity ≥ 0.45 + size within 6%

Current coverage: **252 / 323 items** priced. 71 items have no matching Toast entry.

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
├── update_prices.py             # Sync Standard Selling prices from Toast CSV
├── repopulate_items.py          # Delete all items + recreate from Excel
├── karavan_inventory_manager.py # Inventory Manager report setup
├── karavan_prices.py            # Price management utilities
├── karavan_setup.py             # Initial ERPNext setup
├── migrate_workspaces.py        # Workspace migration
│
├── _ssm_delete_all_items.py     # Force-delete all items via SQL (FOREIGN_KEY_CHECKS=0)
├── _ssm_delete_invoices.py      # Force-delete all invoices and payment entries
├── _ssm_set_cases.py            # Set cases_on_hand via UPC→barcode SQL match
├── _ssm_finish_items.py         # Create remaining items in batches via SSM
├── _ssm_force_4.py              # Direct SQL INSERT for 4 Frappe-sanitizer-blocked items
├── _ssm_fix_stock_validation.py # Mark items as non-stock, enable negative stock
├── _ssm_run.py                  # Generic SSM script runner
│
├── _setup_invoice_deduction.py  # Server scripts: deduct/restore cases_on_hand on invoice submit/cancel
├── _set_query_report.py         # Inventory Manager query report setup
│
├── .env.example                 # Required env vars (copy to .env and fill in)
└── README.md                    # This file
```

---

## Infrastructure

Provisioned via CloudFormation:

| Resource | Details |
|----------|---------|
| EC2 | Single instance running Docker Compose |
| RDS | MariaDB (primary database) |
| ElastiCache | Redis × 2 (cache + queue) |
| S3 | File/attachment storage |
| CloudFront | CDN + HTTPS termination |
| ACM | SSL cert (DNS validated via GoDaddy) |
| SSM | Remote command execution into Docker container |

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

| Issue | Workaround |
|-------|-----------|
| Frappe "format is an unsafe attribute" | Certain item names blocked by sanitizer — use direct SQL INSERT via SSM |
| SSM payload limit 97 KB | Batch items ≤ 50 per SSM call |
| `tabItem Barcode` empty via REST API | Load barcodes via SSM SQL into `_barcodes.json` cache |
| UPC stored as float in Excel | Convert: `str(int(float(upc_raw)))` |
| `tabWebsite Item` doesn't exist on this instance | Wrap each DELETE in try/except |
| Items are non-stock type | ERPNext stock validation bypassed; `cases_on_hand` custom field used instead |

---

*Last updated: 2026-06-29*
