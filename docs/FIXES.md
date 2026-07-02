# Pending Infrastructure Fixes

These fixes ensure all AWS resources are managed by CloudFormation and eliminate out-of-band resource creation.

---

## Fix 4: Put the app behind CloudFront with SSL and a custom domain (GoDaddy)

**Goal**: Replace direct public IP access with a CloudFront distribution fronting the EC2 instance. SSL terminates at CloudFront via ACM. The custom domain (managed in GoDaddy) points to CloudFront. The EC2 instance is no longer directly reachable from the public internet.

---

### Overview of what gets added

```
Browser (HTTPS)
    │
    ▼
CloudFront Distribution  (custom domain + ACM SSL cert)
    │
    ▼ HTTP on port 80 (private origin, EC2 Elastic IP)
EC2 instance  (nginx → ERPNext containers)
```

---

### 4a. Add an ACM Certificate (CloudFormation)

**File to modify**: `cloudformation/erpnext-poc.yaml`

Add a parameter for the domain:

```yaml
DomainName:
  Type: String
  Description: Primary domain name for the app (e.g. erp.example.com or example.com).

AlternateDomainName:
  Type: String
  Default: ''
  Description: Optional www or additional subdomain (e.g. www.example.com). Leave blank if not needed.
```

Add an ACM certificate resource. **Must use DNS validation** — email validation does not work well with CloudFormation as it requires manual inbox action:

```yaml
SSLCertificate:
  Type: AWS::CertificateManager::Certificate
  Properties:
    DomainName: !Ref DomainName
    SubjectAlternativeNames:
      - !If [HasAlternateDomain, !Ref AlternateDomainName, !Ref AWS::NoValue]
    ValidationMethod: DNS
    Tags:
      - Key: Name
        Value: !Sub ${AWS::StackName}-ssl-cert
```

Add the condition:

```yaml
HasAlternateDomain: !Not [!Equals [!Ref AlternateDomainName, '']]
```

**Important**: CloudFormation will pause at this resource until DNS validation records are confirmed in GoDaddy (see step 4c). The certificate ARN is output for use in CloudFront.

---

### 4b. Add a CloudFront Distribution (CloudFormation)

**File to modify**: `cloudformation/erpnext-poc.yaml`

Add this resource after the certificate:

```yaml
CloudFrontDistribution:
  Type: AWS::CloudFront::Distribution
  Properties:
    DistributionConfig:
      Enabled: true
      Comment: !Sub ${AWS::StackName} ERPNext distribution
      Aliases:
        - !Ref DomainName
        - !If [HasAlternateDomain, !Ref AlternateDomainName, !Ref AWS::NoValue]
      ViewerCertificate:
        AcmCertificateArn: !Ref SSLCertificate
        SslSupportMethod: sni-only
        MinimumProtocolVersion: TLSv1.2_2021
      Origins:
        - Id: ERPNextEC2
          DomainName: !Ref ERPNextEIP
          CustomOriginConfig:
            HTTPPort: 80
            OriginProtocolPolicy: http-only
      DefaultCacheBehavior:
        TargetOriginId: ERPNextEC2
        ViewerProtocolPolicy: redirect-to-https
        AllowedMethods: [GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE]
        CachedMethods: [GET, HEAD]
        CachePolicyId: 4135ea2d-6df8-44a3-9df3-4b5a84be39ad  # CachingDisabled managed policy
        OriginRequestPolicyId: 216adef6-5c7f-47e4-b989-5492eafa07d3  # AllViewer managed policy — forwards all headers, cookies, query strings
        Compress: true
      HttpVersion: http2and3
      PriceClass: PriceClass_100
      Tags:
        - Key: Name
          Value: !Sub ${AWS::StackName}-cloudfront
```

**Notes on cache policy**:
- `CachingDisabled` is intentional — ERPNext is a dynamic ERP, caching responses would break it.
- `AllViewer` origin request policy forwards all headers and cookies so ERPNext sessions work correctly.
- WebSocket (Socket.IO) connections work through CloudFront automatically with `http2and3` and `AllowedMethods` set to all.

Add to Outputs:

```yaml
CloudFrontDomain:
  Description: CloudFront distribution domain name — use this as the CNAME target in GoDaddy
  Value: !GetAtt CloudFrontDistribution.DomainName

CloudFrontDistributionId:
  Description: CloudFront distribution ID
  Value: !Ref CloudFrontDistribution
```

---

### 4c. Lock down EC2 to only accept traffic from CloudFront

Once CloudFront is in place, the EC2 instance should not be reachable directly on port 80 from the public internet. Update the `EC2SecurityGroup` in CloudFormation to replace the open HTTP rule:

```yaml
# Remove this rule:
- IpProtocol: tcp
  FromPort: 80
  ToPort: 80
  CidrIp: 0.0.0.0/0
  Description: HTTP

# Replace with (restrict to CloudFront managed prefix list):
- IpProtocol: tcp
  FromPort: 80
  ToPort: 80
  SourcePrefixListId: pl-3b927c52   # AWS managed prefix list for CloudFront (us-east-1)
  Description: HTTP from CloudFront only
```

The prefix list ID `pl-3b927c52` is the AWS-managed list of CloudFront edge node IPs for us-east-1. This ensures only CloudFront can reach the origin — direct IP access is blocked.

Also remove the Elastic IP output `ERPNextURL` (or update it to show the CloudFront URL instead) so developers don't accidentally share the direct IP.

---

### 4d. GoDaddy DNS — developer instructions

The developer needs to make two sets of changes in GoDaddy DNS. CloudFormation will output the values needed.

**Step 1 — ACM certificate validation (do this first, while CF stack is deploying)**

When the `SSLCertificate` resource is being created, the AWS Console (or CLI) will show one or two CNAME records that must be added to GoDaddy to prove domain ownership. These look like:

```
Type:  CNAME
Name:  _abc123def456.erp.example.com
Value: _xyz789.acm-validations.aws.
TTL:   600
```

Add these records in GoDaddy (Domains → DNS → Add Record). CloudFormation will not proceed past the certificate resource until these are confirmed. Validation typically takes 2–5 minutes once the records propagate.

**Step 2 — Point the domain to CloudFront**

After the stack finishes deploying, get the CloudFront domain from the stack output `CloudFrontDomain`. It will look like `d1abc2defg3hij.cloudfront.net`.

Add the following in GoDaddy DNS:

| Scenario | Record type | Name | Value |
|---|---|---|---|
| Subdomain (e.g. `erp.example.com`) | CNAME | `erp` | `d1abc2defg3hij.cloudfront.net` |
| Apex domain (`example.com`) | ALIAS / ANAME | `@` | `d1abc2defg3hij.cloudfront.net` |
| www redirect | CNAME | `www` | `d1abc2defg3hij.cloudfront.net` |

GoDaddy supports ALIAS (also called ANAME) records for apex domains pointing to CloudFront. If GoDaddy's UI shows only A/CNAME options for `@`, use the ALIAS type — it behaves like a CNAME at the root.

Set TTL to 600 (10 minutes) initially; raise it to 3600 once confirmed working.

**Step 3 — Verify**

Once DNS propagates (5–30 minutes), confirm:
- `https://erp.example.com` loads ERPNext
- HTTP redirects to HTTPS
- The SSL certificate shows as valid (issued by Amazon)
- Direct IP access (`http://<elastic-ip>`) returns a connection refused or timeout

---

### 4e. Update the GitHub OIDC role permissions

**File to modify**: `cloudformation/github-oidc.yaml`

Add CloudFront and ACM permissions so the deploy role can manage these new resources:

```yaml
- Sid: CloudFront
  Effect: Allow
  Action:
    - cloudfront:CreateDistribution
    - cloudfront:UpdateDistribution
    - cloudfront:DeleteDistribution
    - cloudfront:GetDistribution
    - cloudfront:GetDistributionConfig
    - cloudfront:TagResource
    - cloudfront:ListDistributions
  Resource: "*"

- Sid: ACM
  Effect: Allow
  Action:
    - acm:RequestCertificate
    - acm:DescribeCertificate
    - acm:DeleteCertificate
    - acm:ListCertificates
    - acm:AddTagsToCertificate
  Resource: "*"
```

---

### Summary of what the developer needs to do manually (in GoDaddy)

1. While the CF stack is deploying — add the ACM DNS validation CNAME records (values come from AWS Console / stack events)
2. After the stack finishes — add a CNAME or ALIAS record pointing the domain to the CloudFront domain name (from stack output `CloudFrontDomain`)
3. Test HTTPS access and confirm direct IP is blocked

---

## Fix 1: Delete the duplicate CloudWatch alarms workflow

**File to delete**: `.github/workflows/setup-cloudwatch-alarms.yml`

**Why**: The CloudFormation template `cloudformation/erpnext-poc.yaml` already defines 4 CloudWatch alarms and an SNS topic (resources `EC2StatusAlarm`, `EC2CPUAlarm`, `RDSFreeStorageAlarm`, `RDSCPUAlarm`, `AlarmTopic`). This workflow creates a second set of alarms via AWS CLI with different names and inconsistent thresholds (CPU at 90% vs 80% in CF), outside of CloudFormation state. Resources created this way are invisible to CloudFormation and will not be cleaned up on stack destroy.

**Action**: Delete the file `.github/workflows/setup-cloudwatch-alarms.yml` entirely.

---

## Fix 2: Add port 443 to the EC2 security group in CloudFormation

**File to modify**: `cloudformation/erpnext-poc.yaml`

**Why**: The `setup-https.yml` workflow adds port 443 to the EC2 security group using `aws ec2 authorize-security-group-ingress`. This creates drift — CloudFormation owns that security group, and any stack update that touches the SG will wipe the manually-added rule. Port 443 must be declared in the template.

**Action**:

1. Add a new parameter `EnableHTTPS` to the Parameters section:

```yaml
EnableHTTPS:
  Type: String
  Default: 'false'
  AllowedValues:
    - 'true'
    - 'false'
  Description: Set to true to open port 443 (HTTPS) on the EC2 security group.
```

2. Add a Condition for it:

```yaml
HTTPSEnabled: !Equals [!Ref EnableHTTPS, 'true']
```

3. Add a conditional ingress rule to the `EC2SecurityGroup` resource, inside `SecurityGroupIngress`:

```yaml
- !If
  - HTTPSEnabled
  - IpProtocol: tcp
    FromPort: 443
    ToPort: 443
    CidrIp: 0.0.0.0/0
    Description: HTTPS
  - !Ref AWS::NoValue
```

**Note**: The `setup-https.yml` workflow itself (nginx installation via SSM) is fine to keep — it configures software on the instance, not AWS resources. Only the `aws ec2 authorize-security-group-ingress` call in that workflow becomes redundant once CF owns the rule. That step can be removed from the workflow or left as a no-op (it will error gracefully with "already exists").

---

## Fix 3: Add multi-environment support (dev / prod)

**Goal**: A single CloudFormation template and deploy workflow that can deploy to isolated `dev` and `prod` environments, with all secrets and environment-specific values stored in GitHub Secrets scoped per environment.

---

### 3a. Add `Environment` parameter to CloudFormation

**File to modify**: `cloudformation/erpnext-poc.yaml`

Add to the `Parameters` section:

```yaml
Environment:
  Type: String
  AllowedValues:
    - dev
    - prod
  Description: Deployment environment. Controls resource sizing and naming.
```

Use it to drive environment-aware sizing via Mappings:

```yaml
Mappings:
  EnvConfig:
    dev:
      InstanceType: t3.micro
      DBInstanceClass: db.t3.micro
      DBAllocatedStorage: '20'
      CacheNodeType: cache.t3.micro
      MultiAZ: false
      BackupRetentionPeriod: 1
    prod:
      InstanceType: t3.large
      DBInstanceClass: db.t3.medium
      DBAllocatedStorage: '100'
      CacheNodeType: cache.t3.medium
      MultiAZ: true
      BackupRetentionPeriod: 7
```

Replace hardcoded values in resources with Mapping lookups, e.g.:

```yaml
# EC2
InstanceType: !FindInMap [EnvConfig, !Ref Environment, InstanceType]

# RDS
DBInstanceClass: !FindInMap [EnvConfig, !Ref Environment, DBInstanceClass]
AllocatedStorage: !FindInMap [EnvConfig, !Ref Environment, DBAllocatedStorage]
MultiAZ: !FindInMap [EnvConfig, !Ref Environment, MultiAZ]
BackupRetentionPeriod: !FindInMap [EnvConfig, !Ref Environment, BackupRetentionPeriod]

# ElastiCache
CacheNodeType: !FindInMap [EnvConfig, !Ref Environment, CacheNodeType]
```

Remove the existing `InstanceType` parameter (it is replaced by the Mapping).

---

### 3b. Update the deploy workflow to accept an environment input

**File to modify**: `.github/workflows/deploy-infra.yml`

1. Add an `environment` input to `workflow_dispatch`:

```yaml
inputs:
  environment:
    description: Target environment
    required: true
    default: dev
    type: choice
    options:
      - dev
      - prod
```

2. Derive the stack name from the environment input:

```yaml
- name: Set stack name
  run: echo "STACK_NAME=erpnext-${{ inputs.environment }}" >> $GITHUB_ENV
```

3. Pass `Environment` and all secrets as CloudFormation parameters, sourcing secrets from the GitHub environment:

```yaml
- name: Deploy CloudFormation stack
  uses: aws-actions/configure-aws-credentials@v6.1.2   # already present
  ...

- name: Deploy stack
  run: |
    aws cloudformation deploy \
      --stack-name $STACK_NAME \
      --template-file cloudformation/erpnext-poc.yaml \
      --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
      --parameter-overrides \
        Environment=${{ inputs.environment }} \
        KeyPairName=${{ secrets.KEY_PAIR_NAME }} \
        AllowedSSHCidr=${{ secrets.ALLOWED_SSH_CIDR }} \
        DBPassword=${{ secrets.DB_PASSWORD }} \
        DBRootPassword=${{ secrets.DB_ROOT_PASSWORD }} \
        AdminPassword=${{ secrets.ADMIN_PASSWORD }} \
        NotificationEmail=${{ secrets.NOTIFICATION_EMAIL }} \
        EnableHTTPS=${{ secrets.ENABLE_HTTPS }}
```

4. Wire the job to use the GitHub Environment so secrets are scoped correctly:

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}   # <-- this scopes secrets to the env
```

---

### 3c. Configure GitHub Environments and Secrets

In the GitHub repository settings, create two Environments: `dev` and `prod`.

Set the following secrets on **each environment** (Settings → Environments → [env] → Secrets):

| Secret name | Description |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | ARN of the IAM role for this environment |
| `KEY_PAIR_NAME` | EC2 key pair name for this environment |
| `ALLOWED_SSH_CIDR` | Your IP in CIDR notation (e.g. `203.0.113.10/32`) |
| `DB_PASSWORD` | MariaDB erpnext user password |
| `DB_ROOT_PASSWORD` | MariaDB root password |
| `ADMIN_PASSWORD` | ERPNext Administrator password |
| `NOTIFICATION_EMAIL` | Alert email (leave blank to disable) |
| `ENABLE_HTTPS` | `true` or `false` |

Remove any repository-level secrets that duplicate these — environment-scoped secrets take precedence and are safer.

---

### 3d. Update the GitHub OIDC IAM role to cover both stack names

**File to modify**: `cloudformation/github-oidc.yaml`

The CloudFormation resource ARN is currently locked to `stack/erpnext-poc/*`. Broaden it to cover both environments:

```yaml
# Replace this:
Resource: !Sub arn:aws:cloudformation:*:${AWS::AccountId}:stack/erpnext-poc/*

# With this:
Resource:
  - !Sub arn:aws:cloudformation:*:${AWS::AccountId}:stack/erpnext-dev/*
  - !Sub arn:aws:cloudformation:*:${AWS::AccountId}:stack/erpnext-prod/*
```

Also update the S3 scope in the same role to cover both environment bucket prefixes:

```yaml
# Replace this:
Resource:
  - !Sub arn:aws:s3:::erpnext-poc-*
  - !Sub arn:aws:s3:::erpnext-poc-*/*

# With this:
Resource:
  - !Sub arn:aws:s3:::erpnext-dev-*
  - !Sub arn:aws:s3:::erpnext-dev-*/*
  - !Sub arn:aws:s3:::erpnext-prod-*
  - !Sub arn:aws:s3:::erpnext-prod-*/*
```

**Note**: Consider deploying separate OIDC roles per environment (`GitHubActions-ERPNext-Dev` and `GitHubActions-ERPNext-Prod`) with tighter scoping. This prevents a compromised dev deployment from touching prod resources. Each environment in GitHub would then have its own `AWS_DEPLOY_ROLE_ARN` secret pointing to the appropriate role.

---

## Fix 5: Remove all "POC" references

The project has moved past proof-of-concept. All POC labels must be removed from filenames, template content, workflow files, and documentation.

### Files to rename

| Old name | New name |
|---|---|
| `cloudformation/erpnext-poc.yaml` | `cloudformation/erpnext.yaml` |

### cloudformation/erpnext.yaml (after rename)

- Line 2: Change `Description` from `ERPNext POC on AWS ...` to `ERPNext on AWS ...`
- Line 361: Change `PolicyName: ERPNextPOCAccessPolicy` to `PolicyName: ERPNextAccessPolicy`

### cloudformation/github-oidc.yaml

- Line 4: Remove "erpnext-poc stack" from description
- Line 32: Remove "erpnext-poc CloudFormation stack" from role description
- Line 65: Remove POC comment
- Line 77: Change `stack/erpnext-poc/*` to `stack/erpnext/*` (or `stack/erpnext-dev/*` + `stack/erpnext-prod/*` if Fix 3 is applied first)
- Lines 106–107: Change `erpnext-poc-*` S3 bucket prefix to `erpnext-*`

### .github/workflows/deploy-infra.yml

- Line 9: Change path trigger from `cloudformation/erpnext-poc.yaml` to `cloudformation/erpnext.yaml`
- Line 27: Change `STACK_NAME: erpnext-poc` to `STACK_NAME: erpnext` (or make dynamic per Fix 3)
- Line 28: Change `TEMPLATE_FILE: cloudformation/erpnext-poc.yaml` to `TEMPLATE_FILE: cloudformation/erpnext.yaml`

### .github/workflows/destroy-stack.yml

- Lines 32, 35, 41, 44: Replace all `erpnext-poc` stack name references with `erpnext`

### .github/workflows/restart-containers.yml

- Stack name filter: change `Values=erpnext-poc` to `Values=erpnext`

### .github/workflows/setup-https.yml

- Stack name filter: change `Values=erpnext-poc` to `Values=erpnext`

### .github/workflows/configure-autostart.yml

- Stack name filter: change `Values=erpnext-poc` to `Values=erpnext`

### .github/workflows/verify-backups.yml

- Stack name filter: change `Values=erpnext-poc` to `Values=erpnext`
- Note: the hardcoded S3 bucket name (`erpnext-poc-erpnextbucket-780m8mqa8l0v`) is a live deployed resource name — it will change naturally when the stack is redeployed under the new name. Do not rename it manually.

### .github/workflows/setup-cloudwatch-alarms.yml

- Stack name filter: change `Values=erpnext-poc` to `Values=erpnext`
- Note: this file is also being deleted per Fix 1. Apply whichever fix runs first.

### ARCHITECTURE.md

- Line 3: `ERPNext on AWS — POC Deployment` → `ERPNext on AWS`
- Line 6: Remove `Production POC (approved for implementation)` → `Production`
- Line 127: Update S3 bucket name example (auto-generated, will change with stack rename)
- Lines 250–251: Remove POC references from architecture decisions table
- Line 260: `Estimated Monthly Cost (POC)` → `Estimated Monthly Cost`
- Line 289: Update filename reference to `erpnext.yaml`

### INFRA-REVIEW.md

- All occurrences of "POC" — replace with "initial deployment" or remove the qualifier entirely where it no longer applies
- This file is largely historical; consider archiving it or removing it once the new architecture is fully deployed

---

## Fix 6: Add .env.template for local stack deployment

**Goal**: Developers should never paste secrets into the command line or hardcode them. A `.env.template` file documents every required variable; developers copy it to `.env`, fill it in, and source it before running the deploy command locally.

### Create `.env.template` (new file in repo root)

```
# ERPNext AWS Infrastructure — Local Deployment Variables
# Copy this file to .env and fill in real values before deploying.
#   cp .env.template .env
#
# .env is gitignored and must NEVER be committed.
# All values here map directly to CloudFormation parameters.

# ── AWS ───────────────────────────────────────────────────────────────────────

AWS_REGION=us-east-1

# IAM role assumed for deployment (from cloudformation/github-oidc.yaml output)
AWS_DEPLOY_ROLE_ARN=arn:aws:iam::ACCOUNT_ID:role/GitHubActions-ERPNext-Deploy

# ── Environment ───────────────────────────────────────────────────────────────

# Target environment: dev or prod
# Controls stack name (erpnext-dev / erpnext-prod) and resource sizing
ENVIRONMENT=dev

# ── Access ────────────────────────────────────────────────────────────────────

# Name of an existing EC2 key pair in the target AWS account
KEY_PAIR_NAME=your-keypair-name

# Your public IP in CIDR notation — restricts SSH access to this IP only
# Find yours: curl -s https://checkip.amazonaws.com
ALLOWED_SSH_CIDR=YOUR_PUBLIC_IP/32

# ── ERPNext ───────────────────────────────────────────────────────────────────

ERPNEXT_VERSION=v15

# ERPNext Administrator account password (min 12 characters)
ADMIN_PASSWORD=CHANGE_ME_MIN_12_CHARS

# ── Database ──────────────────────────────────────────────────────────────────

# MariaDB erpnext user password (min 12 characters)
DB_PASSWORD=CHANGE_ME_MIN_12_CHARS

# MariaDB root password stored in Secrets Manager (min 12 characters)
DB_ROOT_PASSWORD=CHANGE_ME_MIN_12_CHARS

# ── Compute ───────────────────────────────────────────────────────────────────

# EC2 instance type
# dev:  t3.micro
# prod: t3.large
INSTANCE_TYPE=t3.micro

# ── Networking / HTTPS ────────────────────────────────────────────────────────

# Open port 443 on the EC2 security group (true/false)
ENABLE_HTTPS=false

# ── Domain (CloudFront — Fix 4) ───────────────────────────────────────────────

# Primary domain name for the CloudFront distribution (e.g. erp.example.com)
DOMAIN_NAME=erp.yourdomain.com

# Optional www or alternate subdomain — leave blank if not needed
ALTERNATE_DOMAIN_NAME=

# ── Monitoring ────────────────────────────────────────────────────────────────

# Email address for CloudWatch alarm notifications — leave blank to disable
NOTIFICATION_EMAIL=
```

### Update `.gitignore`

Add `!.env.template` after the existing `!.env.example` line so the template is tracked by git but `.env` (with real values) remains ignored:

```
!.env.example
!.env.template   # add this line
```

### Update `README.md`

Replace the existing deploy section (which references the old `erpnext-poc.env.example`) with:

```markdown
## Deploy locally

1. Copy `.env.template` to `.env` and fill in all values:
   cp .env.template .env

2. Source the file and deploy:

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
    InstanceType=$INSTANCE_TYPE \
    EnableHTTPS=$ENABLE_HTTPS \
    DomainName=$DOMAIN_NAME \
    NotificationEmail=$NOTIFICATION_EMAIL
```
