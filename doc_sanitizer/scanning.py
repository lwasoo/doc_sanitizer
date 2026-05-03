from __future__ import annotations

from pathlib import Path
from typing import Any

from report_converter.common import log, normalize_text
from .document_io import collect_texts_for_path, default_sanitized_path, ensure_supported_path
from .llm_assist import collect_llm_candidates
from .mapping import merge_entries, normalize_entries, read_mapping, refresh_payload_metadata
from .patterns import extract_contextual_candidates, match_candidates_in_text


def build_mapping_payload(
    texts: list[str],
    input_path: Path,
    output_path: Path,
    mapping_path: Path,
    custom_terms: list[str],
    use_llm_assist: bool,
    model: str,
    ollama_url: str,
    timeout_sec: int,
    retries: int,
    existing_entries_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    existing_entries: list[dict[str, Any]] = []
    if existing_entries_override is not None:
        existing_entries = normalize_entries(existing_entries_override)
        log(f"已加载当前内存映射: {len(existing_entries)} 条")
    elif mapping_path.exists():
        try:
            existing_entries = read_mapping(mapping_path).get("entries", [])
            log(f"已加载现有映射: {len(existing_entries)} 条")
        except Exception as exc:
            log(f"读取现有映射失败，将重新生成: {exc}", level="WARN")

    candidates = collect_candidates(texts, custom_terms)
    if use_llm_assist:
        try:
            existing_terms = {normalize_text(str(entry.get("original", ""))) for entry in existing_entries if isinstance(entry, dict)}
            llm_candidates = collect_llm_candidates(
                texts,
                model=model,
                ollama_url=ollama_url,
                timeout_sec=timeout_sec,
                retries=retries,
                rule_candidates=candidates,
                existing_terms=existing_terms,
            )
            if llm_candidates:
                log(f"AI 辅助新增候选: {len(llm_candidates)} 条")
                candidates.extend(llm_candidates)
        except Exception as exc:
            log(f"AI 辅助识别失败，已回退规则模式: {exc}", level="WARN")
    merged = merge_entries(existing_entries, candidates)
    payload = {
        "version": 2,
        "source_file": str(input_path),
        "sanitized_file": str(output_path),
        "entries": merged,
    }
    refresh_payload_metadata(payload)
    log(f"识别到敏感项: {len(payload['entries'])} 条，启用 {len(payload['replacements'])} 条")
    return payload


def collect_candidates(texts: list[str], custom_terms: list[str]) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []

    for term in sorted({normalize_text(x) for x in custom_terms if normalize_text(x)}, key=len, reverse=True):
        candidates.append(("CUSTOM", term, "custom_terms"))

    for text in texts:
        candidates.extend(match_candidates_in_text(text))
        candidates.extend(extract_contextual_candidates(text))

    deduped: dict[str, tuple[str, str]] = {}
    for category, value, source in sorted(candidates, key=lambda item: len(item[1]), reverse=True):
        deduped.setdefault(normalize_text(value), (category, source))
    return [(category, original, source) for original, (category, source) in deduped.items()]


def scan_file_payload(
    input_path: Path,
    custom_terms: list[str] | None = None,
    use_llm_assist: bool = True,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    ollama_url: str = "http://127.0.0.1:11434",
    timeout_sec: int = 120,
    retries: int = 2,
    existing_mapping_path: Path | None = None,
    existing_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_supported_path(input_path)
    output_path = default_sanitized_path(input_path)
    mapping_path = existing_mapping_path or input_path.with_name(f"{input_path.stem}_映射.json")
    texts = collect_texts_for_path(input_path)
    payload = build_mapping_payload(
        texts=texts,
        input_path=input_path,
        output_path=output_path,
        mapping_path=mapping_path,
        custom_terms=custom_terms or [],
        use_llm_assist=use_llm_assist,
        model=model,
        ollama_url=ollama_url,
        timeout_sec=timeout_sec,
        retries=retries,
        existing_entries_override=existing_payload.get("entries", []) if existing_payload else None,
    )
    if existing_payload:
        payload["source_file"] = str(input_path)
    return payload
