#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(id -u)" == 0 ]]; then
  echo 'Run this as the normal Pi user, not with sudo.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip rsync
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[basler]'
.venv/bin/dataset-probe
echo 'Start the service with: .venv/bin/dataset-capture'
