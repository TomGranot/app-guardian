#!/bin/bash
set -e

echo "=== App Guardian setup ==="
echo ""

# Python check
if ! command -v python3 &>/dev/null; then
    echo "❌  python3 not found. Install via: brew install python"
    exit 1
fi
echo "✅  python3: $(python3 --version)"

# apfel check (optional but recommended)
if command -v apfel &>/dev/null; then
    echo "✅  apfel: found"
else
    echo "⚠️   apfel not found — install with:"
    echo "    brew tap Arthur-Ficial/tap && brew install apfel"
    echo "    Requires macOS 26+ (Tahoe) with Apple Intelligence enabled."
    echo "    You can disable Apple Intelligence in the menu and the app still works."
fi
echo ""

# Virtual environment
echo "Creating venv…"
python3 -m venv venv
source venv/bin/activate

echo "Installing dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "✅  Setup complete!"
echo ""
echo "  Start now:          ./run.sh"
echo "  Auto-start on login: ./install-agent.sh"
echo ""
echo "Make sure apfel is installed and running:"
echo "  brew tap Arthur-Ficial/tap && brew install apfel"
echo "  apfel --serve"
