# ERPNext on AWS — Design Document (POC)

> **Status: APPROVED FOR IMPLEMENTATION**
> Approach: Option B — EC2 + frappe_docker + RDS + ElastiCache (single-AZ POC)

---

## Decisions Confirmed

| Decision | Value |
|----------|-------|
| Deployment model | EC2 running `frappe/frappe_docker` (Docker Compose) |
| Availability | Single AZ — POC only, no high availability |
| Database | Amazon RDS for MariaDB (single-AZ) |
| Cache / Queue | Amazon ElastiCache (Redis, single-node) |
| Multi-AZ | ❌ Not for POC |
| Estimated cost | ~$120/mo |

---

## Application Overview

**ERPNext** (`frappe/erpnext`) is a Python/Frappe ERP deployed via Docker Compose (`frappe/frappe_docker`). The official image supports pointing `DB_HOST`, `REDIS_CACHE`, and `REDIS_QUEUE` at external managed AWS services.

### Container Services (all run on the single EC2 host)

| Container | Role |
|-----------|------|
| `backend` | Gunicorn app server (Werkzeug) |
| `frontend` | Nginx — serves static assets, proxies to backend + websocket |
| `websocket` | Node.js Socket.IO for real-time updates |
| `queue-short` | RQ worker — short background jobs |
| `queue-long` | RQ worker — long background jobs |
| `scheduler` | Frappe cron scheduler |
| `configurator` | One-shot init container — writes `common_site_config.json` |

### External AWS Managed Services

| Service | Purpose |
|---------|---------|
| RDS MariaDB | Replaces the `db` container |
| ElastiCache Redis (x2 nodes) | Replaces `redis-cache` + `redis-queue` containers |
| S3 | Backups and file attachments |

---

## AWS Architecture (Single-AZ POC)

```
Internet
    │
    ▼
[Security Group: public-sg]
[EC2 t3.medium]  ──────────────────────────────────────────────┐
│  Docker Compose                                               │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  frontend  │  │ backend  │  │websocket │  │ workers  │  │
│  │  (nginx)   │  │(gunicorn)│  │(node.js) │  │scheduler │  │
│  └─────┬──────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│        │              │              │              │         │
│        └──────────────┴──────────────┴──────────────┘         │
│                          Private VPC                           │
│                  ┌───────────────────────┐                    │
│                  │   [Security Group:    │                    │
│                  │     private-sg]       │                    │
│  ┌───────────────▼──────┐  ┌────────────▼────────────────┐   │
│  │ RDS MariaDB 10.6     │  │ ElastiCache Redis 7.x       │   │
│  │ db.t3.micro          │  │ cache.t3.micro (x2 nodes)   │   │
│  │ Single-AZ, 20GB gp3  │  │ redis-cache + redis-queue   │   │
│  └──────────────────────┘  └─────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                              │
                    [S3 Bucket: backups + files]
```

---

## Resource Specifications

### VPC & Networking

| Resource | Value |
|----------|-------|
| VPC CIDR | `10.0.0.0/16` |
| Public subnet (EC2) | `10.0.1.0/24` — single AZ |
| Private subnet (RDS + Redis) | `10.0.2.0/24` — same AZ |
| Internet Gateway | 1x |
| NAT Gateway | ❌ Not needed (EC2 is in public subnet with outbound via IGW) |

### EC2 Instance

| Property | Value |
|----------|-------|
| Instance type | `t3.medium` (2 vCPU, 4 GB RAM) |
| AMI | Amazon Linux 2023 (latest) |
| Storage | 30 GB gp3 root volume |
| Key pair | Parameter — user supplies at deploy time |
| Elastic IP | 1x (stable public IP for DNS) |
| UserData | Installs Docker, Docker Compose, clones `frappe_docker`, sets env vars, starts stack |

### RDS (MariaDB)

| Property | Value |
|----------|-------|
| Engine | MariaDB 10.6 |
| Instance class | `db.t3.micro` |
| Storage | 20 GB gp3 |
| Multi-AZ | No |
| Publicly accessible | No (private subnet only) |
| Backup retention | 3 days |
| Deletion protection | No (POC) |

### ElastiCache (Redis)

| Cluster | Instance | Purpose |
|---------|----------|---------|
| `erpnext-cache` | `cache.t3.micro` | Frappe session / document cache |
| `erpnext-queue` | `cache.t3.micro` | RQ job queue + Socket.IO pub/sub |

- Engine: Redis 7.x
- Single-node, single-AZ
- No auth token (internal VPC only)

### S3

| Property | Value |
|----------|-------|
| Purpose | ERPNext site backups + file attachments |
| Encryption | SSE-S3 |
| Versioning | Disabled (POC) |
| Public access | Blocked |

### Security Groups

| SG | Inbound Rules |
|----|--------------|
| `ec2-sg` | TCP 22 (SSH) from deployer IP; TCP 80 + 443 from 0.0.0.0/0 |
| `rds-sg` | TCP 3306 from `ec2-sg` only |
| `redis-sg` | TCP 6379 from `ec2-sg` only |

### Secrets Manager

Two secrets created by the stack:

| Secret | Contents |
|--------|---------|
| `erpnext/poc/db` | `db_root_password`, `db_password` |
| `erpnext/poc/app` | `admin_password` |

The EC2 UserData script reads these at boot via AWS CLI before starting Docker Compose.

---

## CloudFormation Template Structure

Single flat template (no nested stacks — keeps the POC simple):

```
erpnext-poc.yaml
│
├── Parameters
│   ├── KeyPairName          — EC2 SSH key
│   ├── AllowedSSHCidr       — Your IP for SSH access
│   ├── ERPNextVersion       — Docker image tag (default: v15)
│   └── DBPassword           — MariaDB root password (NoEcho)
│
├── Resources
│   ├── VPC + subnets + IGW + route tables
│   ├── Security groups (ec2, rds, redis)
│   ├── RDS subnet group + MariaDB instance
│   ├── ElastiCache subnet group + 2x Redis clusters
│   ├── S3 bucket
│   ├── IAM instance role (S3 + Secrets Manager access)
│   ├── EC2 instance (with UserData bootstrap)
│   └── Elastic IP
│
└── Outputs
    ├── ERPNextURL           — http://<ElasticIP>
    ├── EC2PublicIP
    ├── RDSEndpoint
    └── SSHCommand
```

### EC2 UserData flow

1. Install Docker + Docker Compose plugin
2. Clone `frappe/frappe_docker`
3. Fetch DB password from Secrets Manager → write `.env`
4. Set `DB_HOST` → RDS endpoint, `REDIS_CACHE` → ElastiCache cache endpoint, `REDIS_QUEUE` → ElastiCache queue endpoint
5. `docker compose up -d`
6. Wait for services → run `bench new-site` to initialise ERPNext

---

## Estimated Monthly Cost (POC, us-east-1)

| Resource | Est. Cost/mo |
|----------|-------------|
| EC2 t3.medium | ~$30 |
| RDS db.t3.micro MariaDB | ~$15 |
| ElastiCache 2x cache.t3.micro | ~$25 |
| S3 (minimal usage) | ~$1 |
| Elastic IP | ~$4 |
| Data transfer | ~$5 |
| **Total** | **~$80–120/mo** |

---

## Not Included in POC (add for production)

- Multi-AZ RDS + ElastiCache
- Application Load Balancer + ACM TLS certificate
- Auto Scaling
- CloudWatch alarms + dashboards
- WAF
- Separate dev/staging/prod stacks
