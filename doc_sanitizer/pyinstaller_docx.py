"""Compatibility fixes for python-docx inside PyInstaller app bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def _resource_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        root = Path(meipass)
        roots.extend(
            [
                root,
                root.parent / "Resources",
                root.parent / "Frameworks",
            ]
        )

    executable = Path(sys.executable).resolve()
    if executable.name:
        contents = executable.parent.parent
        roots.extend([contents / "Resources", contents / "Frameworks"])

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            unique_roots.append(resolved)
            seen.add(resolved)
    return unique_roots


def _read_template(filename: str) -> bytes:
    candidates = [root / "docx" / "templates" / filename for root in _resource_roots()]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_bytes()
    checked = ", ".join(str(candidate) for candidate in candidates) or "<no PyInstaller roots>"
    raise FileNotFoundError(f"Unable to find python-docx template {filename}; checked: {checked}")


def patch_python_docx_templates() -> None:
    """Make python-docx find bundled templates in macOS PyInstaller app layout."""
    if not getattr(sys, "frozen", False):
        return

    from docx.parts.hdrftr import FooterPart, HeaderPart

    original_header = HeaderPart._default_header_xml
    original_footer = FooterPart._default_footer_xml

    def default_header_xml(cls) -> bytes:
        try:
            return original_header()
        except FileNotFoundError:
            return _read_template("default-header.xml")

    def default_footer_xml(cls) -> bytes:
        try:
            return original_footer()
        except FileNotFoundError:
            return _read_template("default-footer.xml")

    HeaderPart._default_header_xml = classmethod(default_header_xml)
    FooterPart._default_footer_xml = classmethod(default_footer_xml)
