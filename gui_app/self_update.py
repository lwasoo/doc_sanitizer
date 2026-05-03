from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def can_self_update_with_asset(asset_path: Path) -> bool:
    if not is_packaged_app():
        return False
    suffix = asset_path.suffix.lower()
    if sys.platform == "win32":
        return suffix == ".exe"
    if sys.platform == "darwin":
        return suffix in {".zip", ".app"}
    return False


def launch_self_updater(asset_path: Path) -> Path:
    if sys.platform == "win32":
        return launch_windows_self_updater(asset_path)
    if sys.platform == "darwin":
        return launch_macos_self_updater(asset_path)
    raise RuntimeError("当前平台不支持自动替换安装。")


def launch_windows_self_updater(asset_path: Path, app_path: Path | None = None) -> Path:
    current_app = app_path or Path(sys.executable)
    if not can_self_update_with_asset(asset_path):
        raise RuntimeError("当前环境不支持自动替换安装。")
    if not current_app.exists():
        raise RuntimeError(f"找不到当前程序: {current_app}")
    if not asset_path.exists():
        raise RuntimeError(f"找不到更新包: {asset_path}")

    script_path = Path(tempfile.gettempdir()) / "FileToolbox_update.bat"
    script = f"""@echo off
chcp 65001 >nul
set "NEW_EXE={asset_path}"
set "OLD_EXE={current_app}"
set "PID={os.getpid()}"
echo Waiting for FileToolbox to exit...
:waitloop
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto waitloop
)
copy /Y "%NEW_EXE%" "%OLD_EXE%" >nul
if errorlevel 1 (
  echo Update failed. Please replace the file manually.
  pause
  exit /b 1
)
start "" "%OLD_EXE%"
del "%NEW_EXE%" >nul 2>nul
del "%~f0" >nul 2>nul
"""
    script_path.write_text(script, encoding="utf-8")
    subprocess.Popen(["cmd", "/c", "start", "", str(script_path)], close_fds=True)
    return script_path


def find_current_macos_app() -> Path:
    executable = Path(sys.executable).resolve()
    for parent in [executable, *executable.parents]:
        if parent.suffix == ".app" and (parent / "Contents" / "MacOS").exists():
            return parent
    raise RuntimeError("找不到当前 .app，源码运行不支持自动更新。")


def launch_macos_self_updater(asset_path: Path, app_path: Path | None = None) -> Path:
    if not is_packaged_app() or sys.platform != "darwin":
        raise RuntimeError("当前环境不是打包后的 macOS app，不能自动替换。")
    current_app = app_path or find_current_macos_app()
    if not current_app.exists():
        raise RuntimeError(f"找不到当前 app: {current_app}")
    if not asset_path.exists():
        raise RuntimeError(f"找不到更新包: {asset_path}")

    script_path = Path(tempfile.gettempdir()) / "FileToolbox_update.sh"
    work_dir = Path(tempfile.gettempdir()) / "FileToolbox_update_work"
    old_app_parent = current_app.parent
    script = f"""#!/bin/sh
set -eu
NEW_ASSET={sh_quote(asset_path)}
OLD_APP={sh_quote(current_app)}
OLD_PARENT={sh_quote(old_app_parent)}
WORK_DIR={sh_quote(work_dir)}
PID={os.getpid()}

while kill -0 "$PID" 2>/dev/null; do
  sleep 1
done

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

case "$NEW_ASSET" in
  *.zip)
    ditto -x -k "$NEW_ASSET" "$WORK_DIR"
    NEW_APP=$(find "$WORK_DIR" -maxdepth 2 -name "*.app" -type d | head -n 1)
    ;;
  *.app)
    NEW_APP="$NEW_ASSET"
    ;;
  *)
    osascript -e 'display dialog "Update failed: unsupported macOS asset." buttons {{"OK"}}'
    exit 1
    ;;
esac

if [ -z "${{NEW_APP:-}}" ] || [ ! -d "$NEW_APP" ]; then
  osascript -e 'display dialog "Update failed: no .app found in the downloaded package." buttons {{"OK"}}'
  exit 1
fi

rm -rf "$OLD_APP"
ditto "$NEW_APP" "$OLD_PARENT/$(basename "$OLD_APP")"
xattr -dr com.apple.quarantine "$OLD_PARENT/$(basename "$OLD_APP")" 2>/dev/null || true
open "$OLD_PARENT/$(basename "$OLD_APP")"
rm -rf "$WORK_DIR"
rm -f "$NEW_ASSET"
rm -f "$0"
"""
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o755)
    subprocess.Popen(["/bin/sh", str(script_path)], start_new_session=True, close_fds=True)
    return script_path


def sh_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "'\"'\"'") + "'"
