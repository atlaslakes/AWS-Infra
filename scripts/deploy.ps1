param(
    [string]$EnvFile = "configuration/erpnext-poc.env"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-AwsCliCommand {
    $cmd = Get-Command aws -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $fallback = 'C:\Program Files\Amazon\AWSCLIV2\aws.exe'
    if (Test-Path $fallback) {
        return $fallback
    }

    throw 'AWS CLI not found. Install AWS CLI v2 or add aws to PATH.'
}

function Import-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Env file not found: $Path"
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $parts = $line.Split('=', 2)
        if ($parts.Count -ne 2) { return }
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
    }
}

Import-EnvFile -Path $EnvFile

$required = @(
    'STACK_NAME',
    'KEY_PAIR_NAME',
    'ALLOWED_SSH_CIDR',
    'ERPNEXT_VERSION',
    'DB_PASSWORD',
    'DB_ROOT_PASSWORD',
    'ADMIN_PASSWORD',
    'INSTANCE_TYPE'
)

foreach ($name in $required) {
    if ([string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable($name))) {
        throw "Missing required value in ${EnvFile}: $name"
    }
}

$awsArgs = @()
if (-not [string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable('AWS_PROFILE'))) {
    $awsArgs += @('--profile', [System.Environment]::GetEnvironmentVariable('AWS_PROFILE'))
}
if (-not [string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable('AWS_REGION'))) {
    $awsArgs += @('--region', [System.Environment]::GetEnvironmentVariable('AWS_REGION'))
}

$parameterOverrides = @(
    "KeyPairName=$([System.Environment]::GetEnvironmentVariable('KEY_PAIR_NAME'))"
    "AllowedSSHCidr=$([System.Environment]::GetEnvironmentVariable('ALLOWED_SSH_CIDR'))"
    "ERPNextVersion=$([System.Environment]::GetEnvironmentVariable('ERPNEXT_VERSION'))"
    "DBPassword=$([System.Environment]::GetEnvironmentVariable('DB_PASSWORD'))"
    "DBRootPassword=$([System.Environment]::GetEnvironmentVariable('DB_ROOT_PASSWORD'))"
    "AdminPassword=$([System.Environment]::GetEnvironmentVariable('ADMIN_PASSWORD'))"
    "InstanceType=$([System.Environment]::GetEnvironmentVariable('INSTANCE_TYPE'))"
)

$notificationEmail = [System.Environment]::GetEnvironmentVariable('NOTIFICATION_EMAIL')
if (-not [string]::IsNullOrWhiteSpace($notificationEmail)) {
    $parameterOverrides += "NotificationEmail=$notificationEmail"
}

Write-Host 'Deploying CloudFormation stack using local env file...'
$awsExe = Get-AwsCliCommand
$awsCommand = @(
    'cloudformation'
    'deploy'
    '--stack-name'
    [System.Environment]::GetEnvironmentVariable('STACK_NAME')
    '--template-file'
    'erpnext-poc.yaml'
    '--capabilities'
    'CAPABILITY_NAMED_IAM'
    '--parameter-overrides'
)

& $awsExe @awsArgs @awsCommand @parameterOverrides