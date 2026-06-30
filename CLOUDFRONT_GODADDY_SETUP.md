# ERPNext behind CloudFront + SSL + GoDaddy

This runbook puts ERPNext behind CloudFront and removes direct public internet reachability to the EC2 origin.

## 1) Request ACM certificate (must be in us-east-1)

```bash
aws acm request-certificate \
  --region us-east-1 \
  --domain-name www.karavanimports.com \
  --subject-alternative-names karavanimports.com \
  --validation-method DNS
```

Add the returned CNAME validation records in GoDaddy DNS. Wait for certificate status to become `ISSUED`.

## 2) Deploy CloudFront stack

```bash
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name erpnext-cloudfront-prod \
  --template-file aws-infra/cloudformation/cloudfront-erpnext.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    Environment=prod \
    AppOriginDomainName=<your-ec2-public-dns-or-eip-dns> \
    AppOriginProtocolPolicy=http-only \
    DomainName=www.karavanimports.com \
    AlternateDomainName=karavanimports.com \
    AcmCertificateArn=<acm-arn-in-us-east-1> \
    OriginVerifyHeaderName=X-Origin-Verify \
    OriginVerifyHeaderValue=<long-random-secret>
```

Get CloudFront target hostname:

```bash
aws cloudformation describe-stacks \
  --region us-east-1 \
  --stack-name erpnext-cloudfront-prod \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionDomainName'].OutputValue" \
  --output text
```

## 3) Point GoDaddy DNS to CloudFront

In GoDaddy DNS:

1. Create `CNAME` record.
2. `Host`: `www`.
3. `Points to`: CloudFront distribution domain from previous step (example `d123abcxyz.cloudfront.net`).
4. TTL: 600 seconds during migration, then raise after verification.

For root/apex `karavanimports.com`, GoDaddy does not support ALIAS/ANAME flattening to CloudFront. Use GoDaddy domain forwarding from `@` to `https://www.karavanimports.com` (301) or move DNS to a provider with ALIAS support.

## 4) Enforce CloudFront-only origin access

On EC2 (Nginx origin verification):

```bash
sudo ORIGIN_VERIFY_HEADER_NAME=X-Origin-Verify \
     ORIGIN_VERIFY_HEADER_VALUE=<same-secret-used-in-cloudfront-stack> \
     bash aws-infra/scripts/lockdown_origin_nginx.sh
```

Lock origin security group to CloudFront managed prefix list:

```bash
bash aws-infra/scripts/lockdown_origin_security_group.sh us-east-1 <security-group-id> 24.245.45.6/32
```

## 5) Validate

1. `https://www.karavanimports.com` loads successfully.
2. Direct `http://<ec2-public-ip>` returns `403` (or fails to connect after SG lockdown).
3. CloudFront origin health is clean (no sustained 5xx).

## Rollback

1. Temporarily point GoDaddy CNAME back if needed.
2. Restore previous SG ingress on 80/443 for emergency direct access.
3. Disable header check by removing `/etc/nginx/conf.d/cloudfront-origin-verify.conf` and reloading Nginx.
