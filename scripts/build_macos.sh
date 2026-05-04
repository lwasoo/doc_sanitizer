#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="${APP_NAME:-FileToolbox}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

VERSION="${MONTH_REPORT_CONVERTER_VERSION:-}"
if [[ -z "$VERSION" ]]; then
  VERSION="$(git describe --tags --abbrev=0 2>/dev/null || true)"
fi
if [[ -z "$VERSION" ]]; then
  VERSION="0.0.0-dev"
fi
VERSION="${VERSION#v}"
VERSION="${VERSION#V}"
PACKAGE_NAME="v${VERSION}-${APP_NAME}"
echo "[INFO] Stamping app version: $VERSION"
printf '%s\n' "$VERSION" > "$ROOT_DIR/gui_app/version.txt"

echo "[INFO] Installing runtime/build dependencies..."
"$PYTHON_BIN" -m pip cache purge >/dev/null 2>&1 || true
"$PYTHON_BIN" -m pip install --no-cache-dir --upgrade pip
"$PYTHON_BIN" -m pip install --no-cache-dir -r requirements.txt -r requirements-build.txt

echo "[INFO] Cleaning old build artifacts..."
rm -rf build dist

ICON_PNG="$ROOT_DIR/assets/icon.png"
ASSET_ICON_ICNS="$ROOT_DIR/assets/icon.icns"
ICON_ICNS="$ROOT_DIR/build/icon.icns"
ICONSET_DIR="$ROOT_DIR/build/icon.iconset"

if [[ -f "$ASSET_ICON_ICNS" ]]; then
  ICON_ICNS="$ASSET_ICON_ICNS"
  echo "[INFO] Using macOS icon: assets/icon.icns"
elif [[ -f "$ICON_PNG" ]]; then
  echo "[INFO] Generating macOS icon from assets/icon.png..."
  rm -rf "$ICONSET_DIR"
  mkdir -p "$ICONSET_DIR"
  sips -z 16 16 "$ICON_PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
  sips -z 32 32 "$ICON_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "$ICON_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
  sips -z 64 64 "$ICON_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$ICON_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
  sips -z 256 256 "$ICON_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$ICON_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
  sips -z 512 512 "$ICON_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$ICON_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
  cp "$ICON_PNG" "$ICONSET_DIR/icon_512x512@2x.png"
  iconutil -c icns "$ICONSET_DIR" -o "$ICON_ICNS"
else
  echo "[ERROR] Missing assets/icon.png; cannot build macOS app icon." >&2
  exit 1
fi

echo "[INFO] Building macOS app bundle with PyInstaller..."
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$PACKAGE_NAME" \
  --icon "$ICON_ICNS" \
  --hidden-import rapidocr_onnxruntime \
  --collect-all rapidocr_onnxruntime \
  --collect-all onnxruntime \
  --add-data "assets:assets" \
  --add-data "docx_to_ppt_converter.py:." \
  --add-data "office_conversion.py:." \
  --add-data "sanitize_docx.py:." \
  --add-data "doc_sanitizer:doc_sanitizer" \
  --add-data "gui_app:gui_app" \
  --add-data "report_converter:report_converter" \
  gui_converter.py

echo "[INFO] Build completed: ./dist/${PACKAGE_NAME}.app"
