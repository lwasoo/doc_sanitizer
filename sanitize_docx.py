#!/usr/bin/env python3
"""Command-line entrypoint for document sanitization and restore.

The CLI is a thin wrapper around doc_sanitizer APIs. It handles arguments, optional
custom term loading, and output path defaults, but does not own scanning/replacement logic.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from report_converter.common import log
from doc_sanitizer import restore_file, sanitize_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sanitize or restore sensitive content in Word/PPT files.")
    parser.add_argument("mode", choices=["sanitize", "restore"], help="Operation mode")
    parser.add_argument("--input", required=True, type=Path, help="Input Word/PPT path (.doc/.docx/.ppt/.pptx)")
    parser.add_argument("--output", required=True, type=Path, help="Output Word/PPT path (.doc/.docx/.ppt/.pptx)")
    parser.add_argument("--mapping", required=True, type=Path, help="Mapping JSON path")
    parser.add_argument("--terms-file", type=Path, help="Optional custom terms file, one term per line")
    parser.add_argument("--use-llm-assist", dest="use_llm_assist", action="store_true", default=True, help="Use local Ollama model to assist sensitive candidate detection (default: on)")
    parser.add_argument("--no-llm-assist", dest="use_llm_assist", action="store_false", help="Disable local Ollama assist and use rules only")
    parser.add_argument("--model", default="qwen2.5:7b-instruct-q4_K_M", help="Ollama model name for sanitize assist")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama base URL")
    parser.add_argument("--prompt-language", choices=["auto", "zh", "en"], default="auto", help="Prompt language for sanitize assist: auto, zh, or en (default: auto)")
    parser.add_argument("--timeout", type=int, default=120, help="Ollama timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="Ollama retry count")
    return parser.parse_args()


def load_terms(path: Path | None) -> list[str]:
    if not path:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Custom terms file not found: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    args = parse_args()
    try:
        if args.mode == "sanitize":
            sanitize_file(
                input_path=args.input,
                output_path=args.output,
                mapping_path=args.mapping,
                custom_terms=load_terms(args.terms_file),
                use_llm_assist=args.use_llm_assist,
                model=args.model,
                ollama_url=args.ollama_url,
                prompt_language=args.prompt_language,
                timeout_sec=args.timeout,
                retries=args.retries,
            )
        else:
            restore_file(
                input_path=args.input,
                output_path=args.output,
                mapping_path=args.mapping,
            )
        return 0
    except Exception as exc:
        log(f"脱敏流程失败: {exc}", level="ERROR")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
