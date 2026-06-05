#!/bin/bash
cd ~/MHBench
uv run python cli.py -v deploy environments/non-generated/dumbbell.json --project-name dumbbella --c2c-url http://REDACTED_C2_IP:8888
