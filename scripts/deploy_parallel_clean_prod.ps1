param(
    [string]$StackName = "erpnext-prod-parallel-20260616",
    [string]$Region = "us-east-1",
    [string]$TemplateFile = "cloudformation/erpnext.yaml",
    [string]$KeyPairName = "erpnext-key",
    [string]$AllowedSSHCidr = "24.245.45.6/32",
    [string]$ERPNextVersion = "v15",
    [string]$DbPassword = "",
    [string]$DbRootPassword = "",
    [string]$AdminPassword = "",
    [string]$NotificationEmail = "admin@atlaslakes.com"
)

if ([string]::IsNullOrWhiteSpace($DbPassword) -or [string]::IsNullOrWhiteSpace($DbRootPassword) -or [string]::IsNullOrWhiteSpace($AdminPassword)) {
    Write-Error "DbPassword, DbRootPassword, and AdminPassword are required."
    exit 1
}

$ErrorActionPreference = "Stop"

Write-Host "Deploying parallel clean production stack: $StackName"

aws cloudformation deploy `
  --region $Region `
  --stack-name $StackName `
  --template-file $TemplateFile `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    Environment=prod `
    KeyPairName=$KeyPairName `
    AllowedSSHCidr=$AllowedSSHCidr `
    ERPNextVersion=$ERPNextVersion `
    DBPassword=$DbPassword `
    DBRootPassword=$DbRootPassword `
    AdminPassword=$AdminPassword `
    NotificationEmail=$NotificationEmail `
    EnableHTTPS=false `
    DomainName= `
    AlternateDomainName=

if ($LASTEXITCODE -ne 0) {
    Write-Error "CloudFormation deploy failed."
    exit $LASTEXITCODE
}

Write-Host "Stack deployed. Fetching outputs..."
aws cloudformation describe-stacks `
  --region $Region `
  --stack-name $StackName `
  --query "Stacks[0].Outputs" `
  --output table `
  --no-cli-pager
