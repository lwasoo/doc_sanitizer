#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="${APP_NAME:-MonthReportConverter}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

echo "[INFO] Installing runtime/build dependencies..."
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-build.txt

echo "[INFO] Cleaning old build artifacts..."
rm -rf build dist

echo "[INFO] Building macOS app bundle with PyInstaller..."
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --hidden-import rapidocr_onnxruntime \
  --collect-all rapidocr_onnxruntime \
  --collect-all onnxruntime \
  --add-data "docx_to_ppt_converter.py:." \
  --add-data "report_converter:report_converter" \
  gui_converter.py

echo "[INFO] Build completed: ./dist/${APP_NAME}.app"
