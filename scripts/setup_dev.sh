#!/usr/bin/env bash
set -e
echo "🏎️ Setting up F1 Telemetry development environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pre-commit install
echo "✓ Dev environment ready! Run 'pytest' to verify tests."
