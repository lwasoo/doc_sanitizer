#!/usr/bin/env python3
"""CLI entrypoint for DOCX -> PPT conversion."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_converter.engine import convert, log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert legal monthly DOCX report into PPT template.")
    parser.add_argument("--docx", required=True, type=Path, help="Input DOCX path")
    parser.add_argument("--template", required=True, type=Path, help="Template PPTX path")
    parser.add_argument("--output", required=True, type=Path, help="Output PPTX path")
    parser.add_argument("--model", default="qwen2.5:7b-instruct-q4_K_M", help="Ollama model name")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama base URL")
    parser.add_argument("--timeout", type=int, default=180, help="Ollama timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="Ollama retry count")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM and use rule mode only")
    parser.add_argument(
        "--layout-mode",
        choices=["classic", "formal"],
        default="formal",
        help="PPT content layout mode (title is always preserved)",
    )
    parser.add_argument(
        "--theme",
        choices=["formal_blue", "corporate_gray", "legal_red"],
        default="formal_blue",
        help="Theme palette for formal layout mode",
    )
    parser.add_argument(
        "--diversity",
        choices=["none", "low", "medium", "high"],
        default="medium",
        help="Layout variety level for formal mode",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed for reproducible layout selection")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        convert(
            docx_path=args.docx,
            template_pptx=args.template,
            output_pptx=args.output,
            model=args.model,
            ollama_url=args.ollama_url,
            timeout_sec=args.timeout,
            retries=args.retries,
            use_llm=not args.no_llm,
            layout_mode=args.layout_mode,
            theme=args.theme,
            diversity=args.diversity,
            seed=args.seed,
        )
        return 0
    except Exception as exc:
        log(f"转换失败: {exc}", level="ERROR")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
