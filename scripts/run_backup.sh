#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d .venv ]; then
  source .venv/bin/activate
fi
export PYTHONPATH=src
python -m netbackup.backup --inventory config/devices.yml
