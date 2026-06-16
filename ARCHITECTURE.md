# AWS Infrastructure Architecture Overview

**Project**: ERPNext on AWS — POC Deployment  
**Stack**: CloudFormation + GitHub Actions + Docker Compose  
**Region**: us-east-1  
**Status**: Production POC (approved for implementation)

---

## Architecture Diagram

```
Internet
    │
    ▼
Internet Gateway
    │
    ▼ (port 80 / 443)
┌───────────────────────────────────────────────────────────────────┐
│  VPC: 10.0.0.0/16                                                 │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Public Subnet: 10.0.1.0/24 (AZ-a)                         │  │
│  │                                                             │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │  EC2 t3.micro (Elastic IP)                           │  │  │
│  │  │  Amazon Linux 2023                                   │  │  │
│  │  │                                                      │  │  │
│  │  │  Docker Compose (frappe_docker v15)                  │  │  │
│  │  │  ├── nginx frontend   (port 80/443)                  │  │  │
│  │  │  ├── backend (gunicorn :8000)                        │  │  │
│  │  │  ├── websocket / socket.io (:9000)                   │  │  │
│  │  │  ├── queue-short (RQ worker)                         │  │  │
│  │  │  ├── queue-long  (RQ worker)                         │  │  │
│  │  │  ├── scheduler (frappe cron)                         │  │  │
│  │  │  └── configurator (one-shot init)                    │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Private Subnet A: 10.0.2.0/24 (AZ-a)                      │  │
│  │  Private Subnet B: 10.0.3.0/24 (AZ-b)                      │  │
│  │                                                             │  │
│  │  ┌──────────────────┐   ┌─────────────────────────────┐   │  │
│  │  │  RDS MariaDB 10.6│   │  ElastiCache Redis 7.0      │   │  │
│  │  │  db.t3.micro     │   │  ├── redis-cache  (cache)   │   │  │
│  │  │  20 GB gp3       │   │  └── redis-queue  (jobs)    │   │  │
│  │  │  Encrypted       │   │  cache.t3.micro × 2         │   │  │
│  │  └──────────────────┘   └─────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘

Supporting Services (outside VPC)
├── S3 Bucket          — encrypted, versioned backups + file attachments
├── Secrets Manager    — DB passwords, admin password
├── SSM               — remote operations & audit trail
├── CloudWatch        — EC2/RDS alarms
├── SNS               — email alert delivery
└── IAM               — EC2 instance role, GitHub OIDC federation role
```

---

## AWS Resources

### Networking

| Resource | Value | Purpose |
|---|---|---|
| VPC | 10.0.0.0/16 | Isolated network for all resources |
| Public Subnet | 10.0.1.0/24 (AZ-a) | EC2 instance with internet access |
| Private Subnet A | 10.0.2.0/24 (AZ-a) | RDS + ElastiCache |
| Private Subnet B | 10.0.3.0/24 (AZ-b) | RDS subnet group failover slot |
| Internet Gateway | — | Routes public subnet traffic to internet |
| Elastic IP | Static | Fixed public IP for EC2 |
| Route Tables | Public + Private | Traffic routing rules |

#### Security Groups

| Name | Inbound Rules | Purpose |
|---|---|---|
| ec2-sg | SSH (22) from configured CIDR; HTTP (80) from 0.0.0.0/0 | EC2 instance access |
| rds-sg | MySQL (3306) from ec2-sg only | Database — no public access |
| redis-sg | Redis (6379) from ec2-sg only | Cache/queue — no public access |

---

### Compute

**EC2 Instance**
- **Type**: t3.micro (configurable: t3.medium, t3.large)
- **AMI**: Amazon Linux 2023 (latest, resolved at deploy time)
- **Storage**: 30 GB gp3 root volume
- **IAM Role**: Grants access to Secrets Manager, SSM agent, S3
- **Bootstrap**: UserData script installs Docker, fetches secrets, clones frappe_docker, starts ERPNext stack
- **Purpose**: Runs the entire ERPNext application via Docker Compose

---

### Database

**RDS MariaDB 10.6**
- **Instance**: db.t3.micro
- **Storage**: 20 GB gp3, encrypted at rest
- **Networking**: Private subnets only, not publicly accessible
- **Backup**: 1-day retention + snapshot on deletion
- **Deletion protection**: Enabled
- **Purpose**: Primary ERPNext database (customers, invoices, inventory, etc.)

---

### Caching & Queuing

**ElastiCache Redis 7.0 — two independent single-node clusters**

| Cluster | Name | Purpose |
|---|---|---|
| Cache | redis-cache | ERPNext document/session caching |
| Queue | redis-queue | RQ job queue + Socket.IO pub/sub for real-time updates |

Both run on cache.t3.micro nodes in the private subnet.

---

### Storage

**S3 Bucket** (auto-named: `erpnext-poc-erpnextbucket-xxx`)
- Server-side encryption (SSE-S3)
- Versioning enabled
- All public access blocked
- **Purpose**: Database backups and ERPNext file attachments; daily sync from EC2

---

### Secrets Management

**AWS Secrets Manager — 2 secrets**

| Secret | Contents | Used By |
|---|---|---|
| DBSecret | `db_root_password`, `db_password` | EC2 UserData at bootstrap, RDS |
| AppSecret | `admin_password` | Docker Compose ERPNext configurator |

Passwords are never stored in CloudFormation parameters or on disk.

---

### Monitoring & Alerting

**CloudWatch Alarms (4)**

| Alarm | Metric | Threshold | Period |
|---|---|---|---|
| EC2 Status Check | StatusCheckFailed | ≥ 1 | 60s × 2 |
| EC2 High CPU | CPUUtilization | > 80% | 300s × 2 |
| RDS Storage Low | FreeStorageSpace | < 5 GB | 300s × 2 |
| RDS High CPU | CPUUtilization | > 80% | 300s × 2 |

**SNS Topic** — conditional; created only if a notification email is provided. Delivers all alarm events via email.

---

### Identity & Access

**IAM Resources**

| Resource | Purpose |
|---|---|
| EC2 Instance Role | Allows EC2 to read Secrets Manager, use SSM agent, read/write S3 |
| GitHub OIDC Role (`GitHubActions-ERPNext-Deploy`) | Lets GitHub Actions assume AWS permissions without storing long-lived credentials; scoped to specific repo/branches |

The GitHub OIDC role (defined in `cloudformation/github-oidc.yaml`) grants permissions for CloudFormation, EC2, RDS, ElastiCache, S3, Secrets Manager, SSM, and IAM management.

---

### Systems Manager (SSM)

SSM is used for all remote operations — no open SSH required in production.

**SSM document library** (`/configuration/` and `/production instance/`): 100+ JSON documents covering:
- Instance bootstrap and site setup
- Container restart, start, stop, status
- Database queries and migrations
- Backup sync to S3
- Health checks and diagnostics
- Sample data creation

---

## Application Stack (Docker Compose)

Seven containers run on the EC2 instance, all from `frappe/erpnext:v15`:

| Container | Exposed Port | Purpose |
|---|---|---|
| frontend (nginx) | 80 → host | Reverse proxy; routes HTTP to backend and websocket |
| backend (gunicorn) | 8000 (internal) | ERPNext application server |
| websocket | 9000 (internal) | Socket.IO for real-time UI updates |
| queue-short | — | RQ worker for short background jobs |
| queue-long | — | RQ worker for long background jobs |
| scheduler | — | Frappe cron — triggers scheduled tasks |
| configurator | — | One-shot init: writes DB/Redis config to `common_site_config.json` |

The frontend container connects to the externally-managed RDS and ElastiCache clusters (not containerised databases).

---

## CI/CD — GitHub Actions Workflows (19 total)

### Infrastructure Management

| Workflow | Trigger | What It Does |
|---|---|---|
| `deploy-infra.yml` | Push to main (on CF template change) or manual | Validates + deploys/updates the CloudFormation stack via OIDC |
| `destroy-stack.yml` | Manual only (requires typing "destroy") | Deletes the CloudFormation stack |
| `setup-cloudwatch-alarms.yml` | Manual | Creates/removes SNS topic + 3 CloudWatch alarms |

### Operations

| Workflow | Trigger | What It Does |
|---|---|---|
| `restart-containers.yml` | Manual | Runs docker compose restart/stop/start/status via SSM SendCommand |
| `setup-https.yml` | Manual | Installs self-signed cert + nginx TLS reverse proxy, or removes it |
| `configure-autostart.yml` | Manual | Installs/removes systemd service so ERPNext restarts on EC2 reboot |
| `verify-backups.yml` | Manual or daily 6am UTC | Lists S3 backups, checks recency, triggers fresh backup + S3 sync |

### ERPNext Data Operations (all manual, all use REST API)

| Workflow | ERPNext DocType |
|---|---|
| `add-customer.yml` | Customer |
| `add-supplier.yml` | Supplier |
| `add-item.yml` | Item |
| `add-invoice.yml` | Sales Invoice |
| `add-lead.yml` | Lead (CRM) |
| `add-opportunity.yml` | Opportunity (CRM) |
| `create-purchase-order.yml` | Purchase Order |
| `create-quotation.yml` | Quotation |
| `add-project.yml` | Project |
| `add-task.yml` | Task |
| `add-stock-entry.yml` | Stock Entry |
| `list-records.yml` | Any DocType (filterable query) |

---

## Key Architecture Decisions

| Decision | Rationale |
|---|---|
| Single-AZ POC | Simplicity + cost; clear upgrade path to multi-AZ for production |
| EC2 + Docker Compose (not ECS/EKS) | Easiest frappe_docker deployment pattern; avoids container orchestration complexity for POC |
| External RDS + ElastiCache | Data durability and managed backups without container-volume risk |
| Secrets Manager (not Parameter Store) | Passwords never touch CloudFormation parameters or disk |
| GitHub OIDC (no stored AWS keys) | Eliminates long-lived credential risk in GitHub |
| SSM over SSH | Audit trail, no need to open port 22 publicly in production |
| Two Redis clusters | Separation of caching and job queue traffic; independent failure domains |

---

## Estimated Monthly Cost (POC)

| Resource | Est. Cost |
|---|---|
| EC2 t3.micro | ~$10 |
| RDS db.t3.micro | ~$15 |
| ElastiCache 2× cache.t3.micro | ~$25 |
| S3 (minimal data) | ~$1 |
| Elastic IP | ~$4 |
| Data transfer | ~$5 |
| **Total** | **~$60/month** |

Cost scales to ~$80–120/month if EC2 is upgraded to t3.medium or t3.large.

---

## Planned Integrations

**Toast POS → ERPNext** (`TOAST-ERPNEXT-PLAN.md`)  
Architecture: Toast webhook → AWS Lambda → ERPNext REST API  
Covers: Chart of accounts, item master sync, warehouse mapping, customer/supplier records, payment mode mapping.

---

## Repository Structure

```
AWS-Infra/
├── cloudformation/
│   ├── erpnext-poc.yaml      Main infrastructure stack (VPC, EC2, RDS, Redis, S3, IAM, CloudWatch)
│   └── github-oidc.yaml      One-time OIDC federation setup for GitHub Actions
├── .github/workflows/        19 GitHub Actions workflows (infra + ops + ERPNext API)
├── configuration/            SSM document library (100+ JSON docs for remote ops)
├── production instance/      Production-specific SSM documents
├── docker/
│   └── pwd-managed.yml       Docker Compose definition for ERPNext v15
└── scripts/                  Python helper scripts (bulk import, dashboard setup, pricing rules)
```
