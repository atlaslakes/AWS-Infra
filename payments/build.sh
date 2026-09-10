#!/usr/bin/env bash
# Builds the deployment zip for the ACH payments Lambdas.
#
#   payments/build.sh [OUTPUT_ZIP]
#
# Produces a zip whose root contains the handler packages (link_token/,
# exchange_and_attach/, dwolla_webhook/, plaid_webhook/, autopay_scan/, common/)
# plus all third-party dependencies. Handler paths in payments-backend.yaml are
# "<pkg>.handler.handler", so those package dirs must sit at the zip root.
#
# Dependencies are installed for the running interpreter's platform. Some deps
# (cryptography via pyjwt[crypto], pydantic-core via plaid-python) are compiled
# extensions, and plaid-python is sdist-only — so this MUST run on Linux x86_64
# (the CI runner is ubuntu-latest). On macOS/Windows, run it inside Docker:
#
#   docker run --rm -v "$PWD":/w -w /w public.ecr.aws/lambda/python:3.12 \
#     bash -c "pip install -q pip -U && payments/build.sh /w/payments-lambda.zip"
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HERE/dist/payments-lambda.zip}"
BUILD_DIR="$HERE/build"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "WARNING: not running on Linux — compiled deps will be wrong for Lambda." >&2
  echo "         Build in CI (ubuntu) or the Docker one-liner in this script's header." >&2
fi

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$(dirname "$OUT")"

echo "==> Installing dependencies into build/"
pip install \
  --requirement "$HERE/requirements.txt" \
  --target "$BUILD_DIR" \
  --upgrade

echo "==> Adding handler source"
cp -r "$HERE/lambdas/." "$BUILD_DIR/"

echo "==> Pruning junk"
find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$BUILD_DIR" -type d -name "*.dist-info" -prune -exec rm -rf {} +
find "$BUILD_DIR" -type d -name "tests" -prune -exec rm -rf {} +
# boto3/botocore ship in the Lambda runtime — drop them to stay small.
rm -rf "$BUILD_DIR"/boto3 "$BUILD_DIR"/botocore "$BUILD_DIR"/s3transfer \
       "$BUILD_DIR"/boto3-* "$BUILD_DIR"/botocore-* 2>/dev/null || true

echo "==> Zipping -> $OUT"
rm -f "$OUT"
python - "$BUILD_DIR" "$OUT" <<'PY'
import os, sys, zipfile
src, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(src):
        for f in files:
            if f.endswith(".pyc"):
                continue
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, src))
PY

echo "==> Done: $(du -h "$OUT" | cut -f1)  $OUT"
