#!/bin/bash
cd ~/MHBench
uv run python cli.py -v deploy environments/non-generated/enterprise_b.json --project-name enterpriseb --c2c-url http://REDACTED_C2_IP:8888
