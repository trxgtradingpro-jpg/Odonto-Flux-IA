#!/usr/bin/env bash
set -euo pipefail

cd /app
python -m app.scripts.seed
