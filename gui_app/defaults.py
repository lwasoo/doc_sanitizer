"""Application constants and version discovery helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def load_app_version() -> str:
    env_version = (
        os.environ.get("FILE_TOOLBOX_VERSION", "").strip()
        or os.environ.get("MONTH_REPORT_CONVERTER_VERSION", "").strip()
    )
    if env_version:
        return env_version.removeprefix("v").removeprefix("V")
    git_version = load_git_version()
    if git_version:
        return git_version
    version_file = Path(__file__).with_name("version.txt")
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version.removeprefix("v").removeprefix("V")
    return "0.0.0-dev"


def load_git_version() -> str:
    root = Path(__file__).resolve().parent.parent
    try:
        completed = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
    except Exception:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip().removeprefix("v").removeprefix("V")


APP_NAME = "FileToolbox"
APP_DISPLAY_NAME = "文件工具箱"
APP_VERSION = load_app_version()
GITHUB_REPO = "lwasoo/doc_sanitizer"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DEFAULT_MODEL = "qwen2.5:7b-instruct-q4_K_M"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
