"""GitHub release check and asset download helpers."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

from ..defaults import APP_VERSION, GITHUB_LATEST_RELEASE_API


@dataclass
class ReleaseAsset:
    name: str
    download_url: str


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    release_name: str
    release_url: str
    published_at: str
    assets: list[ReleaseAsset]
    is_update_available: bool

    @property
    def preferred_download_url(self) -> str:
        if not self.assets:
            return self.release_url
        platform_keys = ["windows", ".exe"] if sys.platform == "win32" else ["macos", ".zip", ".app"]
        for asset in self.assets:
            name = asset.name.lower()
            if any(key in name for key in platform_keys):
                return asset.download_url
        return self.assets[0].download_url

    @property
    def preferred_asset_name(self) -> str:
        if not self.assets:
            return ""
        preferred_url = self.preferred_download_url
        for asset in self.assets:
            if asset.download_url == preferred_url:
                return asset.name
        return self.assets[0].name


def fetch_latest_release(timeout_sec: int = 8) -> UpdateInfo:
    req = urllib.request.Request(
        GITHUB_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FileToolbox-update-checker",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法连接 GitHub Releases: {exc}") from exc

    latest_version = normalize_version(str(payload.get("tag_name", "")))
    if not latest_version:
        raise RuntimeError("GitHub Releases 返回中缺少版本号。")

    assets = [
        ReleaseAsset(name=str(asset.get("name", "")), download_url=str(asset.get("browser_download_url", "")))
        for asset in payload.get("assets", [])
        if isinstance(asset, dict) and asset.get("browser_download_url")
    ]
    return UpdateInfo(
        current_version=APP_VERSION,
        latest_version=latest_version,
        release_name=str(payload.get("name", "")) or f"v{latest_version}",
        release_url=str(payload.get("html_url", "")) or "https://github.com/lwasoo/doc_sanitizer/releases/latest",
        published_at=str(payload.get("published_at", "")),
        assets=assets,
        is_update_available=compare_versions(latest_version, APP_VERSION) > 0,
    )


def download_release_asset(info: UpdateInfo, dest_dir: Path | None = None, timeout_sec: int = 60) -> Path:
    if not info.assets:
        raise RuntimeError("当前 Release 没有可下载的安装包，请打开 Release 页面手动查看。")
    url = info.preferred_download_url
    filename = sanitize_filename(info.preferred_asset_name or f"FileToolbox-v{info.latest_version}")
    target_dir = dest_dir or default_download_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_path(target_dir / filename)
    req = urllib.request.Request(url, headers={"User-Agent": "FileToolbox-update-downloader"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp, target.open("wb") as fh:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"下载更新包失败: {exc}") from exc
    return target


def default_download_dir() -> Path:
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        return downloads
    return Path.home()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip()
    return cleaned or "FileToolbox-update"


def normalize_version(version: str) -> str:
    return version.strip().removeprefix("v").removeprefix("V")


def compare_versions(left: str, right: str) -> int:
    left_key = version_key(left)
    right_key = version_key(right)
    for left_part, right_part in zip_longest(left_key, right_key, fillvalue=0):
        if left_part > right_part:
            return 1
        if left_part < right_part:
            return -1
    return 0


def version_key(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", normalize_version(version))
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts)
