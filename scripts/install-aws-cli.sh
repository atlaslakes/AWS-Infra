#!/usr/bin/env bash
# install-aws-cli.sh — installs AWS CLI v2 on Linux (x86_64) and configures it from .env

set -euo pipefail

echo "==> Checking for existing AWS CLI installation..."
if command -v aws &>/dev/null; then
  echo "AWS CLI already installed: $(aws --version)"
  exit 0
fi

echo "==> Downloading AWS CLI v2..."
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip

echo "==> Extracting..."
unzip -q /tmp/awscliv2.zip -d /tmp/awscli-install

echo "==> Installing (requires sudo)..."
sudo /tmp/awscli-install/aws/install

echo "==> Cleaning up..."
rm -rf /tmp/awscliv2.zip /tmp/awscli-install

echo "==> Installed: $(aws --version)"

# ── Load credentials from .env ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found at $ENV_FILE"
  exit 1
fi

echo "==> Loading credentials from .env..."
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

# Validate required variables
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is not set in .env}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is not set in .env}"
: "${AWS_DEFAULT_REGION:?AWS_DEFAULT_REGION is not set in .env}"

echo "==> Configuring AWS CLI profile..."
aws configure set aws_access_key_id     "$AWS_ACCESS_KEY_ID"
aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"
aws configure set default.region        "$AWS_DEFAULT_REGION"
aws configure set default.output        "json"

echo "==> Verifying identity..."
aws sts get-caller-identity

echo ""
echo "Done! AWS CLI is installed and authenticated."
