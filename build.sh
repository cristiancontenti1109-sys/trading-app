#!/usr/bin/env bash
set -e

# 1. Build the React frontend
cd web
npm install
npm run build

# 2. Copy built files into backend so it can serve them
mkdir -p ../backend/frontend_dist
cp -r dist/. ../backend/frontend_dist/

# 3. Install Python backend dependencies
cd ../backend
pip install -r requirements.txt
