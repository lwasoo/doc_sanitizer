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
    vbs_path = Path(tempfile.gettempdir()) / "FileToolbox_update.vbs"
    target_app = windows_update_target_path(asset_path, current_app)
    log_path = Path(tempfile.gettempdir()) / "FileToolbox_update.log"
    script = build_windows_update_script(
        asset_path=asset_path,
        current_app=current_app,
        target_app=target_app,
        pid=os.getpid(),
        script_path=script_path,
        vbs_path=vbs_path,
        log_path=log_path,
    )
    script_path.write_text(script, encoding="utf-8")
    vbs_path.write_text(
        f'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.Run Chr(34) & "{script_path}" & Chr(34), 0, False\n',
        encoding="utf-8",
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["wscript.exe", str(vbs_path)], close_fds=True, creationflags=creationflags)
    return script_path


def windows_update_target_path(asset_path: Path, current_app: Path) -> Path:
    return current_app.parent / asset_path.name


def build_windows_update_script(
    asset_path: Path,
    current_app: Path,
    target_app: Path,
    pid: int,
    script_path: Path,
    vbs_path: Path,
    log_path: Path,
) -> str:
    same_source_and_target = asset_path.resolve() == target_app.resolve()
    copy_block = (
        'copy /Y "%NEW_EXE%" "%TARGET_EXE%" >>"%LOG%" 2>&1\n'
        "if errorlevel 1 exit /b 1"
        if not same_source_and_target
        else 'echo Downloaded exe is already in the target path. >>"%LOG%"'
    )
    cleanup_download = 'del "%NEW_EXE%" >nul 2>nul' if not same_source_and_target else ""
    return f"""@echo off
chcp 65001 >nul
set "NEW_EXE={asset_path}"
set "OLD_EXE={current_app}"
set "TARGET_EXE={target_app}"
set "PID={pid}"
set "LOG={log_path}"
echo Waiting for FileToolbox to exit... >"%LOG%"
:waitloop
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto waitloop
)
{copy_block}
if /I not "%OLD_EXE%"=="%TARGET_EXE%" (
  del "%OLD_EXE%" >>"%LOG%" 2>&1
)
start "" "%TARGET_EXE%"
{cleanup_download}
del "{vbs_path}" >nul 2>nul
del "%~f0" >nul 2>nul
"""


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
