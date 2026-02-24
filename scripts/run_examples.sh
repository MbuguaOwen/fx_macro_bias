#!/usr/bin/env bash
set -euo pipefail

python -m fxbias run
python -m fxbias run --pairs EURUSD GBPUSD USDJPY XAUUSD XAGUSD --format table
python -m fxbias run --format json --out out/bias.json
