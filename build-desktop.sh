#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Step 1/3: Building Python backend with PyInstaller ==="
cd backend

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
pip install -q pyinstaller

rm -rf dist/trading_server build/trading_server
pyinstaller trading_server.spec --noconfirm

echo "Backend binary built: backend/dist/trading_server/"

echo ""
echo "=== Step 2/3: Building React frontend ==="
cd ../web
npm run build

echo ""
echo "=== Step 3/3: Packaging into .dmg ==="
npx electron-builder --mac dmg

echo ""
echo "=== Done! ==="
echo "Your app is at: web/release/"
ls release/*.dmg 2>/dev/null || ls release/mac*/*.dmg 2>/dev/null || true
