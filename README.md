# AWS-Infra

CloudFormation infrastructure for ERPNext POC on AWS.

## Template

- `erpnext-poc.yaml`

## What It Provisions

- VPC, public subnet, and private subnets
- EC2 (`t3.medium` by default) with UserData bootstrap for `frappe_docker`
- RDS MariaDB 10.6 (`db.t3.micro`, single-AZ)
- 2x ElastiCache Redis 7 single-node clusters (`cache.t3.micro`)
- S3 bucket for files/backups
- IAM role/profile for EC2 (Secrets Manager + S3 access)
- Elastic IP and security groups

## Deploy

Safer local workflow:

1. Copy [erpnext-poc.env.example](erpnext-poc.env.example) to `erpnext-poc.env`.
2. Fill in the real values locally.
3. Run `./deploy.ps1` from PowerShell.

```bash
aws cloudformation deploy \
	--stack-name erpnext-poc \
	--template-file erpnext-poc.yaml \
	--capabilities CAPABILITY_NAMED_IAM \
	--parameter-overrides \
		KeyPairName=<your-keypair-name> \
		AllowedSSHCidr=<your-public-ip>/32 \
		ERPNextVersion=v15 \
		DBPassword=<strong-db-password> \
		DBRootPassword=<strong-root-password> \
		AdminPassword=<strong-admin-password>
```

The PowerShell script uses the env file so you do not have to paste secrets into the command line.

The architecture diagram shows a `t3.medium` EC2 host, but this AWS account currently rejects that size change during stack updates. Keep `INSTANCE_TYPE=t3.micro` here unless you are deploying in an account that allows `t3.medium`.

## Validate First

```bash
aws cloudformation validate-template --template-body file://erpnext-poc.yaml
```