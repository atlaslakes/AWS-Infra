# AWS Deployment Plan for ERPNext (Frappe)

This document defines a detailed deployment plan for running ERPNext (Frappe) on AWS with strong backup practices and a strict data residency policy.

## 1. Goals

- Deploy ERPNext on AWS in a production-ready architecture.
- Ensure reliable backups and tested recovery.
- Avoid multi-national redundancy and cross-country data replication.

## 2. Core Constraints

- All production resources must stay in one country.
- Do not replicate data across countries.
- Use one AWS Region that is physically located in the approved country.
- Multi-AZ in the same Region is allowed.
- Cross-Region disaster recovery is allowed only if the secondary Region is in the same country.

## 3. Target AWS Architecture

### 3.1 Networking

- Create one VPC with at least 2 private subnets and 2 public subnets across 2 Availability Zones.
- Place application and database services in private subnets.
- Place ALB (Application Load Balancer) in public subnets.
- Restrict inbound traffic to HTTPS (443) only.
- Use VPC endpoints for S3 and Secrets Manager where possible.

### 3.2 Compute Layer

Choose one deployment model:

- Option A: ECS Fargate (recommended for containerized ERPNext/Frappe).
- Option B: EC2 Auto Scaling Group (if ERPNext requires host-level control).

Minimum production setup:

- 2 or more tasks/instances for web and background workers across 2 AZs.
- Auto scaling based on CPU, memory, and request count.
- Rolling or blue/green deployments.

For ERPNext, run separate process groups:

- `web` service for HTTP requests.
- `socketio` service for realtime events.
- `worker-short`, `worker-default`, `worker-long` for queue processing.
- `schedule` service for cron-like jobs.

### 3.3 Data Layer

- Use a fully managed AWS database tier.
- Preferred: Amazon Aurora MySQL-compatible (managed, HA, autoscaling storage).
- Alternative: Amazon RDS for MariaDB (managed, widely used with ERPNext).
- Enable Multi-AZ for high availability.
- Enable automatic backups and point-in-time recovery.
- Use encrypted storage (KMS-managed keys).

Database operations model (low-ops):

- No self-managed database on EC2.
- Use AWS-managed patching windows and automatic minor version upgrades.
- Use RDS Proxy for connection management and failover resilience.
- Enable Performance Insights and Enhanced Monitoring.
- Use automated backup retention and copy policies.
- Restrict direct DB access; app connects through private endpoints only.

For ERPNext dependencies:

- Use Amazon ElastiCache for Redis with three logical endpoints/usages:
  - Redis cache
  - Redis queue
  - Redis socketio

### 3.4 Storage

- Use Amazon S3 for static assets, exports, and backup artifacts.
- Enable S3 Versioning.
- Enable SSE-KMS encryption.
- Block public access at bucket level.

### 3.5 Security and Access

- Use IAM roles (no long-lived static credentials).
- Store secrets in AWS Secrets Manager.
- Use AWS WAF on ALB for basic web protection.
- Enable CloudTrail, GuardDuty, and Security Hub.
- Use least-privilege IAM policies.

### 3.6 Observability

- Application logs to CloudWatch Logs.
- Metrics and alarms in CloudWatch:
  - ALB 5xx errors
  - ECS/EC2 CPU and memory
  - RDS CPU, free storage, replica lag (if any)
- Notify alerts via SNS (email/Slack integration).

## 4. Deployment Plan (Step by Step)

1. Confirm approved country and AWS Region.
2. Provision network (VPC, subnets, route tables, NAT, security groups).
3. Provision data services (Aurora or RDS, parameter groups, subnet group, backups, proxy).
4. Provision compute platform (ECS service or EC2 ASG).
5. Configure ALB, TLS certificates (ACM), HTTPS listener, target groups.
6. Configure Secrets Manager and application environment variables.
7. Deploy ERPNext application build.
8. Run database migrations.
9. Execute smoke tests and health checks.
10. Enable autoscaling and production alarms.
11. Run backup validation and restore drill before go-live.
12. Cut over traffic and monitor closely for 24-48 hours.

## 4.1 ERPNext-Specific Deployment Fit

This design can host `frappe/erpnext` directly and supports production traffic because it includes:

- Stateless app containers/instances behind ALB.
- Managed MariaDB with Multi-AZ.
- Managed database operations (AWS handles patching, backups, failover mechanics).
- Dedicated Redis roles for cache/queue/socketio.
- Isolated worker services for async jobs.
- TLS termination at ALB and private-only backend tiers.

Recommended compute sizing (starting point):

- Web: 2 tasks, 1 vCPU, 2 GB RAM each.
- Socketio: 2 tasks, 0.5 vCPU, 1 GB RAM each.
- Workers (each queue type): 1-2 tasks, 1 vCPU, 2 GB RAM.
- Scheduler: 1 task, 0.5 vCPU, 512 MB-1 GB RAM.

Scale after load testing based on queue depth, request latency, and worker execution time.

## 4.2 ERPNext Configuration (How It Is Configured)

### A. Required Environment/Secrets

Store in AWS Secrets Manager and inject at runtime:

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `REDIS_CACHE`, `REDIS_QUEUE`, `REDIS_SOCKETIO`
- `SITE_NAME` (for single-site) or site mapping for multi-site
- `FRAPPE_SITE_NAME_HEADER` (usually `Host`)

Use managed endpoints instead of instance IPs:

- `DB_HOST` should point to Aurora/RDS writer endpoint (or RDS Proxy endpoint).
- Keep credentials in Secrets Manager with scheduled rotation.

### B. `common_site_config.json` Pattern

Set these values in the container startup or config volume:

```json
{
  "db_host": "<rds-endpoint>",
  "db_port": 3306,
  "redis_cache": "redis://<cache-endpoint>:6379",
  "redis_queue": "redis://<queue-endpoint>:6379",
  "redis_socketio": "redis://<socketio-endpoint>:6379",
  "socketio_port": 9000
}
```

### C. Site-Level Config

Per-site `site_config.json` should include database name/user and site-specific keys.
Do not store plaintext secrets in source control.

### D. Nginx/Proxy and Realtime

- Route `/socket.io` to the `socketio` service.
- Keep sticky sessions only if required by custom apps.
- Ensure forwarded headers are preserved (`Host`, `X-Forwarded-Proto`).

### E. Background Jobs and Scheduler

- Ensure all worker queues are running continuously.
- Run exactly one scheduler task in production.
- Monitor queue backlog and failed jobs.

### F. Storage and Files

- Keep ERPNext private/public files on durable shared storage.
- Preferred: S3-backed object storage integration for attachments and backups.
- Enforce lifecycle policies and encryption on file buckets.

## 5. Backup Plan

### 5.1 What to Back Up

- RDS database (full and incremental snapshots via automated backups).
- Application configuration and secrets metadata (do not export plaintext secrets).
- S3 business documents and static assets.
- Infrastructure as Code templates and deployment manifests.

### 5.2 Backup Frequency

- RDS automated backups: daily with point-in-time recovery enabled.
- RDS manual snapshot: before every release.
- S3 critical buckets: daily backup via AWS Backup or scheduled replication within same country.
- Configuration export: daily/weekly depending on change rate.

### 5.3 Retention Policy

- Daily backups: keep 30 days.
- Weekly backups: keep 12 weeks.
- Monthly backups: keep 12 months.
- Critical compliance data: retain according to legal policy.

### 5.4 Backup Security

- Encrypt all backups with KMS.
- Restrict restore and delete permissions to a small admin group.
- Enable MFA delete where applicable.
- Log all backup and restore operations via CloudTrail.
- Test a quarterly failover for Aurora/RDS Multi-AZ as part of resilience checks.

### 5.5 Recovery Targets

- Target RPO: 15 minutes or better.
- Target RTO: 2 hours for priority services.

### 5.6 Restore Testing

- Run restore drill monthly in a non-production environment.
- Validate:
  - database integrity
  - application startup
  - key business transactions
- Document each drill result and action items.

## 6. No Multi-National Redundancy Policy

To meet the requirement that there is no redundancy on a multi-national level:

- Primary and standby resources must be in one country only.
- Do not configure cross-country S3 replication.
- Do not configure cross-country RDS snapshot copy.
- Do not deploy read replicas in another country.
- Restrict allowed Regions in IAM/SCP policies.
- Review AWS Backup copy rules to ensure destination stays in-country.

Example controls:

- AWS Organizations SCP: deny resource creation outside approved Region list.
- Config rules: detect resources created in unauthorized Regions.
- Periodic audit: monthly inventory of all resource Regions.

## 7. Release and Change Management

- Use separate environments: dev, staging, production.
- Require successful staging validation before production deployment.
- Use change approval for production releases.
- Keep rollback plan for each release:
  - previous app image
  - pre-release DB snapshot
  - rollback runbook

## 8. Operational Runbooks

Maintain runbooks for:

- Application rollback.
- Database restore.
- TLS certificate renewal.
- Incident response (high error rate, latency spikes, DB outage).
- Region compliance verification.

## 9. Acceptance Checklist

- Architecture deployed and healthy across 2 AZs.
- HTTPS and security controls enabled.
- Backup jobs are running and monitored.
- Restore drill passed.
- No resources outside approved in-country Region set.
- ERPNext business smoke tests passed.

ERPNext-specific acceptance checks:

- Desk login works over HTTPS.
- Realtime notifications and websocket events work.
- Background jobs are processed by all worker queues.
- Scheduled jobs run successfully.
- File upload/download works for public and private files.

## 10. Suggested Next Actions

- Finalize country/Region list and compliance requirements.
- Convert this plan into Infrastructure as Code (Terraform or CloudFormation).
- Add CI/CD pipeline for repeatable deployments.
- Schedule first backup restore drill date.
