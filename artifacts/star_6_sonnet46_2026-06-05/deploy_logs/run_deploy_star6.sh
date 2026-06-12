#!/bin/bash
cd ~/MHBench || exit 9
export PATH="$HOME/.local/bin:$PATH"
echo "=== DEPLOY star_pe (project star6) START $(date -u) ==="
uv run python cli.py -v deploy environments/non-generated/star_pe.json \
  --project-name star6 \
  --c2c-url http://128.105.145.61:8888 2>&1 | tee /tmp/mh_deploy.log
echo "DEPLOY_EXIT=${PIPESTATUS[0]} :: $(date -u)" | tee -a /tmp/mh_deploy.log
