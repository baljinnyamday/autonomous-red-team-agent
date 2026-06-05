#!/bin/bash
set -o pipefail
cd ~/MHBench
export PATH="$HOME/.local/bin:$PATH"
echo "=== DEPLOY dumbbell_pe (project dumbbellb) START $(date -u) ==="
uv run python cli.py -v deploy environments/non-generated/dumbbell_pe.json \
  --project-name dumbbellb \
  --c2c-url http://REDACTED_C2_IP:8888 2>&1
echo "DEPLOY_EXIT=$? $(date -u)"
