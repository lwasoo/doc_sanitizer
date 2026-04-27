from __future__ import annotations

import datetime as dt
import re


def log(message: str, level: str = "INFO") -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {message}", flush=True)


def normalize_text(text: str) -> str:
    text = (text or "").replace("\xa0", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def short_line(text: str, max_len: int | None = None) -> str:
    text = normalize_text(text)
    text = re.sub(r"^[鈥⑩棌\-\d.銆乗s]+", "", text)
    if max_len is not None and len(text) > max_len:
        return text[:max_len]
    return text


def is_heading_candidate(text: str, style: str) -> bool:
    if style in {"Heading 1", "Heading 2", "Title"} and len(text) <= 40:
        return True
    patterns = [
        r"^[一二三四五六七八九十]+\s*[、.]",
        r"^\d+[、.)-]",
        r"^[（(]?[一二三四五六七八九十]+[)）]",
    ]
    if re.search(r"^\d+[、.)-]", text) and len(text) > 20:
        return False
    if any(re.search(p, text) for p in patterns):
        return True
    return len(text) <= 14 and (text.endswith("项") or text.endswith("专项") or text.endswith("工作"))


def section_bucket_for_title(title: str) -> str:
    title = normalize_text(title)
    if "概述" in title:
        return "overview"
    if "基础运作流程数据" in title or ("用印" in title and "专利" in title):
        return "data"
    if "典型协议" in title or "合同管理" in title:
        return "contracts"
    if "知识产权" in title or "IP" in title:
        return "ip"
    if "仲裁" in title or "诉讼" in title:
        return "litigation"
    if "合规" in title or "风险" in title:
        return "compliance"
    return "generic"


def slide_caps(title: str, has_table: bool) -> dict[str, int]:
    bucket = section_bucket_for_title(title)
    if has_table:
        return {"source_limit": 8, "bullet_limit": 4, "bullet_min": 2, "page_size": 2}
    if bucket in {"contracts", "litigation"}:
        return {"source_limit": 28, "bullet_limit": 20, "bullet_min": 6, "page_size": 8}
    if bucket in {"ip", "compliance"}:
        return {"source_limit": 18, "bullet_limit": 14, "bullet_min": 5, "page_size": 7}
    if bucket == "overview":
        return {"source_limit": 14, "bullet_limit": 10, "bullet_min": 4, "page_size": 6}
    return {"source_limit": 12, "bullet_limit": 12, "bullet_min": 5, "page_size": 6}
