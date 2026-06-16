# AWS-Infra

CloudFormation infrastructure for ERPNext on AWS.

## Template

- [cloudformation/erpnext.yaml](cloudformation/erpnext.yaml)
- [cloudformation/github-oidc.yaml](cloudformation/github-oidc.yaml)

## Local Deploy

1. Copy `.env.template` to `.env` and fill in all values.
2. Source the file and deploy.

```bash
source .env && aws cloudformation deploy \
  --stack-name erpnext-${ENVIRONMENT} \
  --template-file cloudformation/erpnext.yaml \
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

## Notes

- The CloudFront distribution fronts the EC2 origin for HTTPS and custom domains.
- DNS validation records for ACM must be added manually in GoDaddy.
- The local `.env` file is intentionally ignored by git.
