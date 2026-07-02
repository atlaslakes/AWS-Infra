# HTTPS Setup Guide for karavanimports.com

## ✅ Completed Steps

### 1. ACM Certificate Requested
- **Certificate ARN**: `arn:aws:acm:us-east-1:319125696520:certificate/d7b7117d-bc80-44c5-878e-cc2b5a112b28`
- **Domains**: `karavanimports.com`, `*.karavanimports.com`
- **Status**: PENDING VALIDATION

### 2. Application Load Balancer Created
- **ALB Name**: `erpnext-prod-alb`
- **ALB DNS**: `erpnext-prod-alb-1243208729.us-east-1.elb.amazonaws.com`
- **ARN**: `arn:aws:elasticloadbalancing:us-east-1:319125696520:loadbalancer/app/erpnext-prod-alb/32040ecf9c118974`
- **Type**: Internet-facing, Application Load Balancer
- **Subnets**: us-east-1a, us-east-1b
- **VPC**: vpc-0a4f6f8ce6afa5c83

### 3. Target Group Created
- **Target Group ARN**: `arn:aws:elasticloadbalancing:us-east-1:319125696520:targetgroup/erpnext-prod-tg/79dae9147ff1bddb`
- **Targets**: EC2 instance (i-02c81e8b43b3a641e) on port 80
- **Health Check**: Path `/`, interval 30s, timeout 5s

### 4. HTTP Listener (→ HTTPS Redirect)
- **Listener ARN**: `arn:aws:elasticloadbalancing:us-east-1:319125696520:listener/app/erpnext-prod-alb/32040ecf9c118974/69263681332550e8`
- **Protocol**: HTTP on port 80
- **Action**: Redirect to HTTPS (301)

---

## ⏳ PENDING: DNS Validation & HTTPS Listener

### Step 1: Add DNS Validation Record

You must add this CNAME record to your domain registrar:

| Name | Type | Value |
|------|------|-------|
| `_63241ccd63f4513b535935fa2487958d.karavanimports.com` | CNAME | `_9f20a01c3cb598d96abc1c93895167c7.jkddzztszm.acm-validations.aws.` |

**Where to add it:**
1. Log into your domain registrar (GoDaddy, Route53, Namecheap, etc.)
2. Find DNS/DNS Settings for `karavanimports.com`
3. Add a new CNAME record with the values above
4. Save changes

**Timeline:** DNS validation typically completes in 1-5 minutes after record creation.

### Step 2: Verify Certificate Validation

Once DNS is added, AWS ACM will automatically validate the certificate. You can check status:

```bash
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:319125696520:certificate/d7b7117d-bc80-44c5-878e-cc2b5a112b28 \
  --region us-east-1 \
  --query "Certificate.Status"
```

Expected output: `ISSUED` (instead of `PENDING_VALIDATION`)

### Step 3: Create HTTPS Listener (After Certificate Validation)

Once certificate is ISSUED, run:

```bash
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:319125696520:loadbalancer/app/erpnext-prod-alb/32040ecf9c118974 \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:us-east-1:319125696520:certificate/d7b7117d-bc80-44c5-878e-cc2b5a112b28 \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:us-east-1:319125696520:targetgroup/erpnext-prod-tg/79dae9147ff1bddb \
  --region us-east-1
```

### Step 4: Point Domain to ALB

Add a DNS record in your registrar to point `karavanimports.com` to the ALB:

| Name | Type | Value |
|------|------|-------|
| `karavanimports.com` | A (or ALIAS/CNAME) | `erpnext-prod-alb-1243208729.us-east-1.elb.amazonaws.com` |

**Note:** 
- If your registrar supports ALIAS/CNAME at apex, use that (recommended for ALBs)
- If only A records, create an alias or CNAME

### Step 5: Verify HTTPS Connection

After all DNS changes propagate (usually 5-10 minutes), test:

```bash
curl -v https://karavanimports.com
```

Expected: 200 OK response from ERPNext, valid TLS certificate

---

## Network Configuration

### Security Group Updates ✅ COMPLETED

The ALB and EC2 instance are now configured to communicate:

**ALB Security Group** (`sg-0c08c79f63de2f1fe`):
- ✅ Inbound: Port 80 from 0.0.0.0/0 (public internet)
- ✅ Inbound: Port 443 from 0.0.0.0/0 (public internet)

**EC2 Security Group** (`sg-0c54ffd3e5e222145`):
- ✅ Inbound: Port 80 from ALB security group (`sg-0c08c79f63de2f1fe`)
- ✅ Inbound: Port 22 from your IP (24.245.45.6/32)

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| ACM Certificate | PENDING_VALIDATION | Waiting for DNS CNAME record |
| ALB | Active | Ready to serve traffic |
| HTTP Listener | Active | Redirects to HTTPS |
| HTTPS Listener | Blocked | Waiting for certificate validation |
| EC2 Instance | Running | Accessible via HTTP from ALB |
| Domain DNS | Pending | Needs CNAME + A record updates |

---

## Direct EC2 Access (Temporary)

While setting up the domain, you can still access ERPNext directly:

- **HTTP**: http://100.57.63.224 (Elastic IP)
- **SSH**: `ssh -i <key> ec2-user@100.57.63.224`

---

## Quick Commands

**Check certificate status:**
```bash
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:319125696520:certificate/d7b7117d-bc80-44c5-878e-cc2b5a112b28 \
  --region us-east-1
```

**Check ALB health:**
```bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:319125696520:targetgroup/erpnext-prod-tg/79dae9147ff1bddb \
  --region us-east-1
```

**Test ALB directly:**
```bash
curl -v http://erpnext-prod-alb-1243208729.us-east-1.elb.amazonaws.com
```

---

## Next Steps

1. **NOW**: Add DNS CNAME record for ACM validation
2. **Wait 1-5 min**: AWS validates the certificate
3. **After validation**: Create HTTPS listener
4. **Add A record**: Point karavanimports.com to ALB
5. **Wait 5-10 min**: DNS propagates
6. **Test**: Access https://karavanimports.com

---

*Document generated: 2026-06-15*
*Stack: erpnext-prod-clean-20260615c*
*Region: us-east-1*
