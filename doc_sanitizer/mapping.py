from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from report_converter.common import normalize_text

@dataclass
class ReplacementItem:
    placeholder: str
    original: str
    category: str
    enabled: bool = True
    source: str = "auto"

def read_mapping(mapping_path: Path) -> dict[str, Any]:
    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    if "entries" in data:
        entries = data["entries"]
    else:
        replacements = data.get("replacements", {})
        categories = data.get("categories", {})
        entries = [
            {
                "placeholder": placeholder,
                "original": str(original),
                "category": str(categories.get(placeholder, "AUTO")),
                "enabled": True,
                "source": "auto",
            }
            for placeholder, original in replacements.items()
        ]
    payload = {
        "version": 2,
        "source_file": data.get("source_file", ""),
        "sanitized_file": data.get("sanitized_file", ""),
        "entries": normalize_entries(entries),
    }
    refresh_payload_metadata(payload)
    return payload

def write_mapping_data(mapping_path: Path, payload: dict[str, Any]) -> None:
    refresh_payload_metadata(payload)
    mapping_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def mapping_entries(payload: dict[str, Any], only_enabled: bool = True) -> list[ReplacementItem]:
    entries = normalize_entries(payload.get("entries", []))
    items: list[ReplacementItem] = []
    for entry in entries:
        if only_enabled and not entry["enabled"]:
            continue
        items.append(
            ReplacementItem(
                placeholder=entry["placeholder"],
                original=entry["original"],
                category=entry["category"],
                enabled=bool(entry.get("enabled", True)),
                source=str(entry.get("source", "auto")),
            )
        )
    return items

def normalize_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for raw in entries:
        placeholder = normalize_text(str(raw.get("placeholder", "")))
        original = normalize_text(str(raw.get("original", "")))
        category = normalize_text(str(raw.get("category", "AUTO"))) or "AUTO"
        enabled = bool(raw.get("enabled", True))
        source = normalize_text(str(raw.get("source", "auto"))) or "auto"
        if not placeholder or not original:
            continue
        key = (placeholder, original)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        out.append(
            {
                "placeholder": placeholder,
                "original": original,
                "category": category.upper(),
                "enabled": enabled,
                "source": source,
            }
        )
    return out

def refresh_payload_metadata(payload: dict[str, Any]) -> None:
    entries = normalize_entries(payload.get("entries", []))
    payload["entries"] = entries
    enabled_entries = [entry for entry in entries if entry["enabled"]]
    counts: dict[str, int] = {}
    for entry in enabled_entries:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    payload["counts"] = counts
    payload["replacements"] = {entry["placeholder"]: entry["original"] for entry in enabled_entries}
    payload["categories"] = {entry["placeholder"]: entry["category"] for entry in enabled_entries}

def compact_entry_placeholders(entries: list[dict[str, Any]]) -> dict[str, str]:
    normalized = normalize_entries(entries)
    grouped: dict[str, list[tuple[bool, int, int, dict[str, Any]]]] = {}
    for order, entry in enumerate(normalized):
        category = str(entry.get("category", "MANUAL")).strip().upper() or "MANUAL"
        grouped.setdefault(category, []).append(
            (bool(entry.get("enabled", True)), parse_placeholder_index(str(entry.get("placeholder", ""))), order, entry)
        )

    changes: dict[str, str] = {}
    for category, rows in grouped.items():
        rows.sort(key=lambda item: (not item[0], item[1] if item[1] > 0 else 10**9, item[2]))
        for new_index, (_enabled, _old_index, _order, entry) in enumerate(rows, start=1):
            old_placeholder = str(entry.get("placeholder", "")).strip()
            new_placeholder = f"__{category}_{new_index:03d}__"
            if old_placeholder != new_placeholder:
                changes[old_placeholder] = new_placeholder
                entry["placeholder"] = new_placeholder

    entries[:] = normalized
    return changes

def merge_entries(existing_entries: list[dict[str, Any]], candidates: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    merged = normalize_entries(existing_entries)
    existing_by_original = {normalize_text(entry["original"]): entry for entry in merged}
    used_placeholders = {entry["placeholder"] for entry in merged}
    counters = category_counters(merged)

    for category, value, source in candidates:
        normalized = normalize_text(value)
        if normalized in existing_by_original:
            continue
        placeholder = next_placeholder(category, counters, used_placeholders)
        entry = {
            "placeholder": placeholder,
            "original": normalized,
            "category": category,
            "enabled": True,
            "source": source,
        }
        merged.append(entry)
        existing_by_original[normalized] = entry
    return merged

def category_counters(entries: list[dict[str, Any]]) -> dict[str, int]:
    counters: dict[str, int] = {}
    for entry in entries:
        category = entry["category"]
        counters[category] = max(counters.get(category, 0), parse_placeholder_index(entry["placeholder"]))
    return counters

def parse_placeholder_index(placeholder: str) -> int:
    match = re.search(r"_(\d{3,})__", placeholder)
    return int(match.group(1)) if match else 0

def next_placeholder(category: str, counters: dict[str, int], used_placeholders: set[str]) -> str:
    category = category.upper()
    while True:
        counters[category] = counters.get(category, 0) + 1
        placeholder = f"__{category}_{counters[category]:03d}__"
        if placeholder not in used_placeholders:
            used_placeholders.add(placeholder)
            return placeholder

def make_manual_entry(original: str, placeholder: str | None = None, category: str = "MANUAL") -> dict[str, Any]:
    original = normalize_text(original)
    placeholder = normalize_text(placeholder or "")
    if not original:
        raise ValueError("敏感词不能为空。")
    if not placeholder:
        placeholder = f"__{category.upper()}_MANUAL__"
    return {
        "placeholder": placeholder,
        "original": original,
        "category": category.upper(),
        "enabled": True,
        "source": "manual",
    }

