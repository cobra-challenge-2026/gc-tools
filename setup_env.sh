#!/usr/bin/env bash
# Create a uv virtual environment for the COBRA2026 gc-tools and install deps.
# Usage:
#   bash setup_env.sh
# Then activate with:
#   source .venv/bin/activate
set -euo pipefail

cd "$(dirname "$0")"

uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r requirements.txt

echo
echo "Done. Activate the environment with:"
echo "    source $(pwd)/.venv/bin/activate"
echo "Verify with:"
echo "    python -c \"import SimpleITK, numpy, scipy, yaml, tqdm, itk; from itk import RTK; print('OK')\""
