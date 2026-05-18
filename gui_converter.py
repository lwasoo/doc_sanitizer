#!/usr/bin/env python3
"""Executable shim for launching the desktop GUI."""

from doc_sanitizer.pyinstaller_docx import patch_python_docx_templates

patch_python_docx_templates()

from gui_app.app import main


if __name__ == "__main__":
    raise SystemExit(main())
