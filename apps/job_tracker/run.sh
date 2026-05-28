#!/bin/bash
# Launch JobTracker Desktop App
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "→ Checking dependencies…"
pip3 install -q PyQt6 flask apscheduler pandas openpyxl 2>/dev/null || true

echo ""
echo "✓ Starting JobTracker Desktop…"
echo ""

python3 desktop_app.py
