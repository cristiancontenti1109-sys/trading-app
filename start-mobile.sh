#!/bin/bash
set -e

cd "$(dirname "$0")/mobile"

if [ ! -d "node_modules" ]; then
  echo "Installing npm packages..."
  npm install
fi

echo "Starting Expo..."
npx expo start
