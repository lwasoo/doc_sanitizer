from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from docx import Document

from .common import is_heading_candidate, log, normalize_text

_OCR_ENGINE: Any | None = None
_OCR_READY = False


def extract_doc_payload(docx_path: Path) -> dict[str, Any]:
    log(f"读取 Word: {docx_path}")
    doc = Document(str(docx_path))

    paragraphs: list[dict[str, Any]] = []
    for p in doc.paragraphs:
        text = normalize_text(p.text)
        blips = p._p.xpath('.//*[local-name()="blip"]')
        image_blobs: list[bytes] = []
        seen_rids: set[str] = set()
        for blip in blips:
            rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            if not rid or rid in seen_rids:
                continue
            seen_rids.add(rid)
            part = doc.part.related_parts.get(rid)
            if part is not None and getattr(part, "blob", None):
                image_blobs.append(part.blob)

        has_drawing = bool(image_blobs)
        if not text and not has_drawing:
            continue
        style = p.style.name if p.style else ""
        paragraphs.append({"text": text, "style": style, "has_drawing": has_drawing, "image_blobs": image_blobs})

    if not paragraphs:
        raise ValueError("DOCX 中没有可用文本。")

    title = paragraphs[0]["text"]
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in paragraphs:
        text = row["text"]
        style = row["style"]
        has_drawing = bool(row.get("has_drawing"))
        image_blobs = row.get("image_blobs", [])
        if text and is_heading_candidate(text, style):
            current = {"heading": text, "items": []}
            sections.append(current)
        elif text:
            if current is None:
                current = {"heading": title, "items": []}
                sections.append(current)
            current["items"].append(text)
        if has_drawing:
            if current is None:
                current = {"heading": title, "items": []}
                sections.append(current)
            current["image_count"] = int(current.get("image_count", 0)) + 1
            imgs = current.setdefault("images", [])
            imgs.extend(image_blobs)

    enrich_sections_with_ocr(sections)

    img_total = sum(int(sec.get("image_count", 0)) for sec in sections)
    log(f"Word 解析完成: {len(paragraphs)} 段, {len(sections)} 个章节, 图片段落 {img_total} 处")
    return {"title": title, "paragraphs": paragraphs, "sections": sections}


def _get_ocr_engine() -> Any | None:
    global _OCR_ENGINE, _OCR_READY
    if _OCR_READY:
        return _OCR_ENGINE
    _OCR_READY = True
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        _OCR_ENGINE = RapidOCR()
        return _OCR_ENGINE
    except Exception as exc:
        log(f"OCR 初始化失败，已跳过图片识别: {exc}", level="WARN")
        _OCR_ENGINE = None
        return None


def extract_text_from_image_bytes(image_blob: bytes) -> str:
    engine = _get_ocr_engine()
    if engine is None:
        return ""
    try:
        from PIL import Image
        import numpy as np

        image = Image.open(io.BytesIO(image_blob)).convert("RGB")
        result, _ = engine(np.array(image))
        if not result:
            return ""
        lines: list[str] = []
        for item in result:
            if not item or len(item) < 2:
                continue
            text = normalize_text(str(item[1]))
            if text:
                lines.append(text)
        return "\n".join(lines)
    except Exception as exc:
        log(f"OCR 识别失败，已跳过单张图片: {exc}", level="WARN")
        return ""


def enrich_sections_with_ocr(sections: list[dict[str, Any]]) -> None:
    for sec in sections:
        images = sec.get("images", []) or []
        ocr_blocks: list[str] = []
        for image_blob in images:
            text = extract_text_from_image_bytes(image_blob)
            if text:
                ocr_blocks.append(text)
        if not ocr_blocks:
            continue
        ocr_text = "\n".join(ocr_blocks)
        sec["ocr_text"] = ocr_text
        sec.setdefault("items", [])
        for item in summarize_ocr_text(ocr_text, normalize_text(str(sec.get("heading", "")))):
            if item and item not in sec["items"]:
                sec["items"].append(item)
        log(f"OCR 已提取章节图片文本: {short_preview(ocr_text)}")


def summarize_ocr_text(ocr_text: str, heading: str) -> list[str]:
    text = normalize_text(ocr_text)
    if not text:
        return []

    lines = [normalize_text(x) for x in ocr_text.splitlines() if normalize_text(x)]
    items: list[str] = []
    if "知识产权" in heading or "专利" in heading or "IP" in heading:
        case_names = extract_ocr_case_names(ocr_text)
        if case_names:
            preview = "；".join(case_names[:6])
            suffix = "等" if len(case_names) > 6 else ""
            items.append(f"图片附表涉及专利事项：{preview}{suffix}")
        bu_hits = sorted(set(re.findall(r"BU\s*1[016]", ocr_text, flags=re.IGNORECASE)))
        if bu_hits:
            bu_norm = [x.replace(" ", "").upper() for x in bu_hits]
            items.append(f"图片附表覆盖业务单元：{'、'.join(bu_norm)}")
    elif lines:
        items.append(f"图片补充信息：{lines[0]}")
    return items


def extract_ocr_case_names(ocr_text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in [normalize_text(x) for x in ocr_text.splitlines()]:
        if not line:
            continue
        if any(prefix in line for prefix in ["ZLSQ-TECH-", "ZLDC-TECH-"]):
            parts = re.split(r"ZLSQ-TECH-\d+|ZLDC-TECH-\d+", line)
            tail = normalize_text(parts[-1] if parts else line)
            if len(tail) >= 4 and tail not in seen:
                seen.add(tail)
                names.append(tail)
                continue
        if len(line) >= 6 and any(key in line for key in ["连接器", "散热", "滤波器", "背板", "footprint", "Amazon", "Nexus"]):
            if line not in seen:
                seen.add(line)
                names.append(line)
    return names[:12]


def detect_month_label(*sources: str) -> str:
    text = " ".join(filter(None, sources))
    m_cn = re.search(r"([一二三四五六七八九十]{1,3})月", text)
    if m_cn:
        return f"{m_cn.group(1)}月份"
    m_num = re.search(r"\b(1[0-2]|[1-9])月", text)
    if m_num:
        return f"{m_num.group(1)}月份"
    month_map = {
        "january": "1",
        "february": "2",
        "march": "3",
        "april": "4",
        "may": "5",
        "june": "6",
        "july": "7",
        "august": "8",
        "september": "9",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    lower = text.lower()
    for eng, num in month_map.items():
        if eng in lower:
            return f"{num}月份"
    return "当月"


def short_preview(text: str, limit: int = 40) -> str:
    text = normalize_text(text)
    return text if len(text) <= limit else f"{text[:limit]}..."
