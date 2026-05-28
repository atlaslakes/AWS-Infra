# set-github-secrets.ps1
# Reads .env and pushes every key=value as a GitHub Actions secret.
# Prerequisites: GitHub CLI installed and authenticated (gh auth login)
# Usage: .\set-github-secrets.ps1

$repo  = "atlaslakes/AWS-Infra"
$env_file = "$PSScriptRoot\..\.env"

if (-not (Test-Path $env_file)) {
    Write-Error ".env file not found at $env_file"
    exit 1
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "GitHub CLI (gh) is not installed. Install from https://cli.github.com"
    exit 1
}

Write-Host "Setting GitHub Actions secrets for $repo ..." -ForegroundColor Cyan

Get-Content $env_file | ForEach-Object {
    # Skip blank lines and comment lines
    if ($_ -match '^\s*$' -or $_ -match '^\s*#') { return }

    $parts = $_ -split '=', 2
    $name  = $parts[0].Trim()
    $value = $parts[1].Trim()

    Write-Host "  -> $name" -ForegroundColor Yellow
    $value | gh secret set $name --repo $repo
}

Write-Host ""
Write-Host "Done. Verify at: https://github.com/$repo/settings/secrets/actions" -ForegroundColor Green
