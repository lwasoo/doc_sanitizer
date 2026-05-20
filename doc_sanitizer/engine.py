"""Public orchestration API for document sanitization and restore.

New code should prefer the object-oriented ``DocumentSanitizer`` service. The functions in
this module remain as stable wrappers for older CLI, GUI, and test imports.
"""

from __future__ import annotations

from pathlib import Path

from .io.operations import apply_mapping_to_docx, apply_mapping_to_file, restore_docx, restore_file
from .mapping import MappingLike, MappingPayload
from .services import DocumentSanitizer

__all__ = [
    "DocumentSanitizer",
    "apply_mapping_to_file",
    "apply_mapping_to_docx",
    "restore_file",
    "restore_docx",
    "sanitize_file",
    "sanitize_docx",
    "scan_file",
    "scan_docx",
]


def sanitizer_for(
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    ollama_url: str = "http://127.0.0.1:11434",
    timeout_sec: int = 120,
    retries: int = 2,
    use_llm_assist: bool = True,
    prompt_language: str = "auto",
) -> DocumentSanitizer:
    return DocumentSanitizer(
        model=model,
        ollama_url=ollama_url,
        timeout_sec=timeout_sec,
        retries=retries,
        use_llm_assist=use_llm_assist,
        prompt_language=prompt_language,
    )


def sanitize_file(
    input_path: Path,
    output_path: Path,
    mapping_path: Path,
    custom_terms: list[str] | None = None,
    use_llm_assist: bool = True,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    ollama_url: str = "http://127.0.0.1:11434",
    timeout_sec: int = 120,
    retries: int = 2,
    prompt_language: str = "auto",
) -> MappingPayload:
    return sanitizer_for(model, ollama_url, timeout_sec, retries, use_llm_assist, prompt_language).sanitize(
        input_path=input_path,
        output_path=output_path,
        mapping_path=mapping_path,
        custom_terms=custom_terms,
    )


def scan_file(
    input_path: Path,
    custom_terms: list[str] | None = None,
    use_llm_assist: bool = True,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    ollama_url: str = "http://127.0.0.1:11434",
    timeout_sec: int = 120,
    retries: int = 2,
    existing_mapping_path: Path | None = None,
    existing_payload: MappingLike | None = None,
    prompt_language: str = "auto",
) -> MappingPayload:
    return sanitizer_for(model, ollama_url, timeout_sec, retries, use_llm_assist, prompt_language).scan(
        input_path=input_path,
        custom_terms=custom_terms,
        existing_mapping_path=existing_mapping_path,
        existing_payload=existing_payload,
    )


def sanitize_docx(
    input_path: Path,
    output_path: Path,
    mapping_path: Path,
    custom_terms: list[str] | None = None,
    use_llm_assist: bool = True,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    ollama_url: str = "http://127.0.0.1:11434",
    timeout_sec: int = 120,
    retries: int = 2,
    prompt_language: str = "auto",
) -> MappingPayload:
    return sanitize_file(
        input_path=input_path,
        output_path=output_path,
        mapping_path=mapping_path,
        custom_terms=custom_terms,
        use_llm_assist=use_llm_assist,
        model=model,
        ollama_url=ollama_url,
        timeout_sec=timeout_sec,
        retries=retries,
        prompt_language=prompt_language,
    )


def scan_docx(
    input_path: Path,
    custom_terms: list[str] | None = None,
    use_llm_assist: bool = True,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    ollama_url: str = "http://127.0.0.1:11434",
    timeout_sec: int = 120,
    retries: int = 2,
    existing_mapping_path: Path | None = None,
    existing_payload: MappingLike | None = None,
    prompt_language: str = "auto",
) -> MappingPayload:
    return scan_file(
        input_path=input_path,
        custom_terms=custom_terms,
        use_llm_assist=use_llm_assist,
        model=model,
        ollama_url=ollama_url,
        timeout_sec=timeout_sec,
        retries=retries,
        existing_mapping_path=existing_mapping_path,
        existing_payload=existing_payload,
        prompt_language=prompt_language,
    )
