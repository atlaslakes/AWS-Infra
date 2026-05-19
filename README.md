# AWS-Infra

This repository manages AWS infrastructure for all projects under this account. It is intended to be consumed and built upon by both humans and AI assistants.

---

## Purpose

Provision and maintain AWS infrastructure using CloudFormation templates, scripts, and configuration files. The repository is organized to clearly separate **account-wide shared infrastructure** from **project-specific infrastructure**.

---

## Repository Structure

```
AWS-Infra/
├ you want to
```

### `account-wide/`
Contains infrastructure that is shared across all projects and provisioned once at the account level. Examples: IAM users for CI/CD, OIDC identity providers, account-level SCPs, shared KMS keys.

### `projects/`
Contains infrastructure scoped to a specific project or application. Each subdirectory is a self-contained project with its own networking, compute, data, and deployment resources.

---

## Phase 1 — Account Bootstrap (Current)

Before any project infrastructure can be deployed via CI/CD, the following one-time setup must be performed **manually by an AWS admin** using the AWS CLI.

### What the bootstrap script does

Located at: `account-wide/bootstrap/bootstrap.sh`

1. Creates an IAM user named `github-runner` to serve as the GitHub Actions service account.
2. Attaches the necessary IAM policies for the runner to deploy infrastructure.
3. Generates an AWS access key pair for the user.
4. Prints the required GitHub secret environment variables to stdout so the admin can register them in GitHub.

> **Note:** This key-based approach is intentionally temporary. The long-term plan is to replace it with a GitHub OIDC identity provider, eliminating the need for long-lived credentials entirely.

### How to run

```bash
# Prerequisites: AWS CLI configured with admin credentials
cd account-wide/bootstrap
chmod +x bootstrap.sh
./bootstrap.sh
```

The script will output something like:

```
=== Add the following secrets to your GitHub repository ===
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

These values must be added to **GitHub → Settings → Secrets and variables → Actions**.

---

## Phase 2 — Project Infrastructure (Next)

Once the bootstrap is complete and GitHub Actions secrets are in place, project infrastructure can be deployed via CI/CD.

The first project is **NextERP** — a production deployment of ERPNext (Frappe) on AWS. See [nexterp/infra.md](nexterp/infra.md) for the full architecture and deployment plan.

High-level order of operations for project infrastructure:

1. **Networking** — VPC, public/private subnets, route tables, NAT gateway, security groups
2. **Data layer** — Aurora/RDS (MariaDB-compatible), ElastiCache (Redis), RDS Proxy
3. **Compute** — ECS Fargate services (web, socketio, workers, scheduler)
4. **Load balancing** — ALB, ACM certificate, HTTPS listener, target groups
5. **Secrets & config** — AWS Secrets Manager, environment variable injection
6. **Observability** — CloudWatch logs, metrics, alarms, SNS notifications
7. **Backups** — Automated RDS snapshots, S3 lifecycle policies, AWS Backup

---

## Instructions for AI Assistants

When helping build out this repository, follow these conventions:

- **Use CloudFormation** (`.yaml`) as the primary IaC format unless a specific alternative is requested.
- **Place account-wide resources** in `account-wide/`. Do not mix them into project folders.
- **Place project resources** in `projects/<project-name>/`. Each project folder should be self-contained.
- **Bootstrap scripts** are plain bash (`.sh`) and must be safe to run with admin AWS CLI credentials. They are run once manually — not by CI/CD.
- **Do not store secrets or credentials** in any file. Secrets are managed in AWS Secrets Manager and injected at runtime.
- **IAM policies** should follow least-privilege. Avoid `*` actions unless explicitly approved.
- **Naming conventions** for AWS resources: use lowercase kebab-case, include the project name as a prefix (e.g. `nexterp-vpc`, `nexterp-web-sg`).
- **The `github-runner` IAM user** is a temporary credential-based service account. When migrating to OIDC, create an OIDC provider and role in `account-wide/` and remove the IAM user.
- **Refer to [nexterp/infra.md](nexterp/infra.md)** for the detailed architecture decisions, constraints, and deployment plan for the NextERP project.

---

## Key Decisions & Constraints

| Decision | Detail |
|---|---|
| IaC format | CloudFormation (YAML) |
| CI/CD auth (current) | IAM user `github-runner` with access keys stored as GitHub secrets |
| CI/CD auth (target) | GitHub OIDC — no long-lived credentials |
| Data residency | All production resources must remain in a single approved country/region |
| Secrets management | AWS Secrets Manager — no plaintext secrets in source control |
| Database | Amazon Aurora MySQL-compatible or RDS MariaDB (Multi-AZ) |
| Compute | ECS Fargate (preferred) |

---

## Contributing

1. All infrastructure changes should go through a pull request.
2. Test CloudFormation templates with `aws cloudformation validate-template` before committing.
3. Bootstrap scripts must be idempotent where possible (safe to re-run).
