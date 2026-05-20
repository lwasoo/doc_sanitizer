"""Object-oriented entry point for scan, sanitize, and restore workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from report_converter.common import log

from ..io.file_types import ensure_supported_path
from ..io.operations import apply_mapping_to_file, restore_file
from ..mapping import MappingLike, MappingPayload
from ..scanning import scan_file_payload


@dataclass
class DocumentSanitizer:
    """Coordinate document scanning, sanitization, and restore operations."""

    model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_url: str = "http://127.0.0.1:11434"
    timeout_sec: int = 120
    retries: int = 2
    use_llm_assist: bool = True
    prompt_language: str = "auto"

    def sanitize(
        self,
        input_path: Path,
        output_path: Path,
        mapping_path: Path,
        custom_terms: list[str] | None = None,
    ) -> MappingPayload:
        ensure_supported_path(input_path)
        payload = self.scan(
            input_path=input_path,
            custom_terms=custom_terms or [],
            existing_mapping_path=mapping_path if mapping_path.exists() else None,
        )
        apply_mapping_to_file(input_path, output_path, payload, mapping_path)
        log(f"脱敏完成: {output_path}")
        log(f"映射文件已输出: {mapping_path}")
        return payload

    def scan(
        self,
        input_path: Path,
        custom_terms: list[str] | None = None,
        existing_mapping_path: Path | None = None,
        existing_payload: MappingLike | None = None,
    ) -> MappingPayload:
        ensure_supported_path(input_path)
        return scan_file_payload(
            input_path=input_path,
            custom_terms=custom_terms,
            use_llm_assist=self.use_llm_assist,
            model=self.model,
            ollama_url=self.ollama_url,
            timeout_sec=self.timeout_sec,
            retries=self.retries,
            prompt_language=self.prompt_language,
            existing_mapping_path=existing_mapping_path,
            existing_payload=existing_payload,
        )

    def restore(
        self,
        input_path: Path,
        output_path: Path,
        mapping_path: Path,
        placeholder_repairs: dict[str, str] | None = None,
    ) -> None:
        restore_file(input_path, output_path, mapping_path, placeholder_repairs=placeholder_repairs)
