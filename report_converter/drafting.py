from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .common import log, normalize_text, section_bucket_for_title, short_line, slide_caps
from .constants import ALL_METRIC_LABELS
from .models import SlideDraft, TemplateSlide


def infer_section_bucket(section: dict[str, Any]) -> str:
    heading = normalize_text(str(section.get("heading", "")))
    body = " ".join(normalize_text(x) for x in section.get("items", [])[:8] if normalize_text(x))
    text = f"{heading} {body}"
    bucket_keywords = {
        "overview": ["概述", "总体", "重大风险", "风险提示", "月报"],
        "data": ["用印", "一般文件", "法律文件", "集团制式", "申请提案统计", "调查统计", "数量", "累计", "基础运作流程"],
        "contracts": ["专案性工作", "合同", "协议", "MPA", "担保", "审核", "保证函", "框架协议", "补充协议"],
        "ip": ["知识产权", "专利", "商标", "337", "OA", "无效", "调查", "申请提案", "Discovery"],
        "litigation": ["诉讼个案", "仲裁", "诉讼", "开庭", "判决", "劳动争议", "被迫解除", "人事争议"],
        "compliance": ["合规", "风险项", "出口管制", "黑名单", "欠款", "社保", "政府项目", "排查"],
    }
    scores: dict[str, int] = {k: 0 for k in bucket_keywords}
    for bucket, words in bucket_keywords.items():
        for word in words:
            if word in text:
                scores[bucket] += 2 if word in heading else 1
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else "generic"


def section_keywords_for_title(title: str) -> list[str]:
    title = normalize_text(title)
    if "概述" in title:
        return ["概述", "总体", "重大风险", "风险提示"]
    if "基础运作流程数据" in title or ("用印" in title and "专利" in title):
        return ["用印", "一般文件", "法律文件", "申请提案统计", "调查统计"]
    if "典型协议与合同管理" in title:
        return ["专案性工作", "合同", "协议"]
    if "知识产权" in title:
        return ["知识产权专项", "知识产权", "IP", "专利申请提案统计", "专利调查统计", "商标事务", "337调查"]
    if "国内仲裁与诉讼个案管理" in title or "仲裁与诉讼" in title:
        return ["诉讼个案", "仲裁", "诉讼", "人事争议"]
    if "合规事务" in title:
        return ["合规与风险项", "合规", "风险项"]
    return []


def keywords_for_title(title: str) -> list[str]:
    title = normalize_text(title)
    mapping = {
        "概述": ["风险", "货款", "诉讼", "合规", "出口管制", "项目", "整改"],
        "基础运作流程数据": ["用印", "申请", "调查", "统计", "数量", "累计"],
        "典型协议与合同管理": ["协议", "合同", "框架", "补充", "审核", "专案"],
        "知识产权": ["专利", "商标", "调查", "337", "无效", "OA", "申请"],
        "仲裁与诉讼": ["仲裁", "诉讼", "开庭", "判决", "调解", "劳动"],
        "合规": ["合规", "排查", "出口", "黑名单", "风险", "整改"],
    }
    out: list[str] = []
    for key, words in mapping.items():
        if key in title:
            out.extend(words)
    return out or [title[:8]]


def preferred_heading_keywords(title: str) -> list[str]:
    title = normalize_text(title)
    if "概述" in title:
        return ["概述"]
    if "典型协议" in title or "合同管理" in title:
        return ["专案性工作"]
    if "知识产权" in title:
        return ["知识产权专项", "知识产权"]
    if "仲裁" in title or "诉讼" in title:
        return ["诉讼个案"]
    if "合规" in title:
        return ["合规与风险项", "合规"]
    return []


def required_terms_for_title(title: str) -> list[str]:
    title = normalize_text(title)
    if "337" in title:
        return ["337"]
    if "美国劳动诉讼" in title:
        return ["美国", "US", "劳动诉讼"]
    return []


def title_profile(title: str) -> dict[str, list[str]]:
    title = normalize_text(title)
    if "概述" in title:
        return {"must_any": ["风险", "货款", "项目", "整改", "排查", "诉讼", "合规"], "avoid": ["用印", "申请提案统计", "调查统计"]}
    if "基础运作流程数据" in title or ("用印" in title and "专利" in title):
        return {"must_any": ["用印", "申请", "调查", "统计", "数量"], "avoid": ["风险", "诉讼", "整改"]}
    if "典型协议" in title or "合同管理" in title:
        return {"must_any": ["协议", "合同", "审核", "框架", "补充", "专案"], "avoid": ["诉讼", "专利调查", "用印"]}
    if "知识产权" in title:
        return {"must_any": ["专利", "商标", "调查", "337", "OA", "无效", "申请提案"], "avoid": ["用印", "劳动争议"]}
    if "仲裁" in title or "诉讼" in title:
        return {"must_any": ["仲裁", "诉讼", "开庭", "判决", "调解", "劳动争议"], "avoid": ["用印", "专利申请提案统计"]}
    if "合规" in title:
        return {"must_any": ["合规", "排查", "出口", "黑名单", "风险", "整改"], "avoid": ["用印", "专利申请提案统计"]}
    return {"must_any": [], "avoid": []}


def matches_title_profile(line: str, title: str) -> bool:
    prof = title_profile(title)
    must_any = prof["must_any"]
    avoid = prof["avoid"]
    if must_any and not any(token in line for token in must_any):
        return False
    if any(token in line for token in avoid):
        return False
    return True


def apply_title_strict_filter(title: str, lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if matches_title_profile(line, title):
            out.append(line)
    return out or lines


def score_line(line: str, keywords: list[str]) -> int:
    line = normalize_text(line)
    score = 0
    for kw in keywords:
        if kw in line:
            score += 2 if len(kw) >= 3 else 1
    if re.search(r"\d", line):
        score += 1
    if any(token in line for token in ["项目", "案件", "协议", "合同", "仲裁", "诉讼", "专利", "商标", "风险"]):
        score += 1
    return score


def is_data_metric_line(line: str) -> bool:
    line = normalize_text(line)
    if not line:
        return False
    data_keywords = ["用印", "一般文件", "法律文件", "集团制式", "申请提案", "专利调查", "统计", "数量", "件", "累计"]
    risk_keywords = ["逾期货款", "风险", "整改", "诉讼", "劳动争议", "排查", "黑名单", "出口管制"]
    return any(k in line for k in data_keywords) and not any(k in line for k in risk_keywords)


def select_source_lines(template_slides: list[TemplateSlide], sections: list[dict[str, Any]]) -> dict[int, list[str]]:
    heading_pairs: list[tuple[str, str]] = []
    all_section_lines: list[str] = []
    for sec in sections:
        heading = normalize_text(sec.get("heading", ""))
        if heading:
            heading_pairs.append((heading, heading))
        for item in sec.get("items", []):
            text = normalize_text(item)
            if text:
                heading_pairs.append((heading, text))
                all_section_lines.append(text)

    selected: dict[int, list[str]] = {}
    for slide in template_slides:
        caps = slide_caps(slide.title, slide.has_table)
        kws = keywords_for_title(slide.title)
        req_terms = required_terms_for_title(slide.title)
        preferred_heads = preferred_heading_keywords(slide.title)
        candidate_pairs = heading_pairs
        section_kws = section_keywords_for_title(slide.title)
        target_bucket = section_bucket_for_title(slide.title)
        section_priority_lines: list[str] = []
        section_has_image = False
        section_has_ocr = False
        strict_section_mode = False

        for sec in sections:
            heading = normalize_text(str(sec.get("heading", "")))
            bucket_match = infer_section_bucket(sec) == target_bucket
            keyword_match = bool(section_kws) and any(k in heading for k in section_kws)
            if keyword_match or bucket_match:
                section_priority_lines.extend([normalize_text(x) for x in sec.get("items", []) if normalize_text(x)])
                if int(sec.get("image_count", 0)) > 0:
                    section_has_image = True
                if normalize_text(str(sec.get("ocr_text", ""))):
                    section_has_ocr = True
        if section_priority_lines:
            strict_section_mode = True
            candidate_pairs = [("", x) for x in section_priority_lines]

        if "基础运作流程数据" in slide.title:
            metric_lines = [x for x in all_section_lines if is_data_metric_line(x)]
            if metric_lines:
                candidate_pairs = [("", x) for x in metric_lines]
                strict_section_mode = True

        if preferred_heads and not strict_section_mode:
            prioritized = [(h, line) for h, line in heading_pairs if any(k in h for k in preferred_heads)]
            if prioritized:
                candidate_pairs = prioritized + [(h, line) for h, line in heading_pairs if (h, line) not in prioritized]

        if strict_section_mode:
            lines = [line for _, line in candidate_pairs][: caps["source_limit"]]
        else:
            ranked = sorted([line for _, line in candidate_pairs], key=lambda x: score_line(x, kws), reverse=True)
            lines = [x for x in ranked if score_line(x, kws) > 0]
        if not lines and strict_section_mode:
            ranked = sorted([line for _, line in heading_pairs], key=lambda x: score_line(x, kws), reverse=True)
            lines = [x for x in ranked if score_line(x, kws) > 0]
        if req_terms:
            lines = [x for x in lines if any(t in x for t in req_terms)]
        if (not strict_section_mode) or ("337" in slide.title) or ("美国劳动诉讼" in slide.title):
            lines = apply_title_strict_filter(slide.title, lines)
        lines = lines[: caps["source_limit"]]

        unique: list[str] = []
        seen: set[str] = set()
        for line in lines:
            sig = line[:24]
            if sig in seen:
                continue
            seen.add(sig)
            unique.append(line)
        if "知识产权" in slide.title and section_has_image and not section_has_ocr:
            log("知识产权章节检测到图片内容：OCR 未生效，请人工补充关键统计。", level="WARN")
        selected[slide.slide_index] = unique[: caps["source_limit"]]
    return selected


def extract_json_object(text: str) -> str:
    payload = text.strip()
    if payload.startswith("{") and payload.endswith("}"):
        return payload
    m = re.search(r"\{[\s\S]*\}", payload)
    if m:
        return m.group(0)
    raise ValueError("LLM 返回中未找到 JSON。")


def call_ollama_json(ollama_url: str, model: str, prompt: str, timeout_sec: int, retries: int) -> dict[str, Any]:
    system_prompt = (
        "你是企业法务月报编辑。"
        "输出只能是严格 JSON。"
        "要写成 PPT 汇报语言，但必须保留关键细节：BU、项目名、案件名、日期、数字。"
    )
    endpoints = [
        ("chat", f"{ollama_url.rstrip('/')}/api/chat"),
        ("generate", f"{ollama_url.rstrip('/')}/api/generate"),
    ]
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        for kind, url in endpoints:
            try:
                log(f"调用 Ollama ({kind}) 第 {attempt} 次: {url}")
                if kind == "chat":
                    body = json.dumps(
                        {
                            "model": model,
                            "format": "json",
                            "stream": False,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                        }
                    ).encode("utf-8")
                else:
                    body = json.dumps(
                        {
                            "model": model,
                            "format": "json",
                            "stream": False,
                            "prompt": f"{system_prompt}\n\n{prompt}",
                        }
                    ).encode("utf-8")
                req = urllib.request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                text = payload.get("message", {}).get("content", "") if kind == "chat" else payload.get("response", "")
                return json.loads(extract_json_object(text))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                log(f"Ollama 调用失败: {exc}", level="WARN")
                continue
    if last_error is None:
        raise RuntimeError("Ollama 调用失败。")
    raise RuntimeError(f"Ollama 调用失败: {last_error}") from last_error


def build_rewrite_prompt(
    report_title: str,
    month_label: str,
    template_slides: list[TemplateSlide],
    selected_sources: dict[int, list[str]],
) -> str:
    blocks: list[str] = []
    for slide in template_slides:
        blocks.append(f"## slide_index={slide.slide_index} | 标题={slide.title}")
        for line in selected_sources.get(slide.slide_index, []):
            blocks.append(f"- {line}")
    source_block = "\n".join(blocks)
    return f"""将素材改写成 PPT 月报要点。

【报告】{report_title}
【月份】{month_label}

【规则】
1. 标题固定，不改标题。
2. 用汇报语气，保留细节：BU、项目、案件、日期、数字。
3. 可缩写，但不得截断句子；不得丢失关键细节。
4. 优先多保留有效 point，单页放不下也继续输出，由程序自动续页。
5. 不要省略号，不要口号句，不要泛化总结。
6. 只输出 JSON。

【输出 JSON】
{{
  "slides":[
    {{"slide_index":2,"bullets":["...","...","..."]}}
  ],
  "metrics": {{
    "一般文件用印":"-",
    "法律文件用印":"-",
    "集团制式文件用印":"-",
    "非制式文件-供应商":"-",
    "非制式文件-客户":"-",
    "非制式文件-内部行政":"-",
    "非制式文件-重要文件":"-",
    "BU10申请量":"-",
    "BU11申请量":"-",
    "BU16申请量":"-",
    "专利调查量BU10":"-",
    "专利调查量BU11":"-",
    "专利调查量BU16":"-",
    "其他知识产权申请":"-"
  }}
}}

【素材池（按页）】
{source_block}
"""


def extract_detail_tokens(line: str) -> list[str]:
    line = normalize_text(line)
    tokens: list[str] = []
    patterns = [
        r"BU\d+",
        r"TA\d+",
        r"\d+\s*月\s*\d+\s*日",
        r"\d+/\d+",
        r"\d+(?:件|万|万元|亿|亿元|天)",
        r"[A-Z]{2,}(?:[-_][A-Z0-9]+)?",
        r"(?:[\u4e00-\u9fff]{2,10}案)",
        r"(?:[\u4e00-\u9fffA-Za-z0-9\-]{2,20}项目)",
    ]
    for pattern in patterns:
        tokens.extend(re.findall(pattern, line))
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def clean_generated_line(line: str) -> str:
    line = normalize_text(line)
    line = re.sub(r"^(?:[-•*]\s*|\d+[.)、]\s*)", "", line)
    line = line.replace("...", "").replace("…", "")
    return line.strip("；;，,。 ")


def abbreviate_for_ppt(text: str) -> str:
    text = normalize_text(text)
    replacements = [
        ("进行", ""),
        ("开展", ""),
        ("相关", ""),
        ("目前", ""),
        ("已经", "已"),
        ("正在", "正"),
        ("对于", "对"),
        ("以及", "及"),
        ("并且", "并"),
    ]
    for src, dst in replacements:
        text = text.replace(src, dst)
    return normalize_text(text)


def compress_for_ppt(line: str, title: str) -> str:
    line = abbreviate_for_ppt(clean_generated_line(line))
    if len(line) <= 80:
        return line
    parts = re.split(r"[；;。]", line)
    parts = [normalize_text(x) for x in parts if normalize_text(x)]
    if len(parts) <= 1:
        return line
    chosen: list[str] = []
    for part in parts:
        if has_specific_signal(part, title):
            chosen.append(part)
        if sum(len(x) for x in chosen) >= 80:
            break
    return "；".join(chosen) if chosen else parts[0]


def detail_fallback_line(source: str, title: str) -> str:
    line = compress_for_ppt(source, title)
    if not has_specific_signal(line, title):
        tokens = extract_detail_tokens(source)
        if tokens:
            line = f"{line}（{ ' / '.join(tokens[:3]) }）"
    return line


def is_too_generic(line: str) -> bool:
    generic_phrases = ["持续推进", "稳步推进", "按计划开展", "有序进行", "完成相关工作", "跟进处理"]
    line = normalize_text(line)
    return any(p in line for p in generic_phrases) or len(extract_detail_tokens(line)) == 0


def has_specific_signal(line: str, title: str) -> bool:
    if extract_detail_tokens(line):
        return True
    profile = title_profile(title)
    return any(token in line for token in profile["must_any"])


def is_near_copy(line: str, sources: list[str]) -> bool:
    key = normalize_text(line)
    for prev in sources:
        prev = normalize_text(prev)
        short, long_ = (key, prev) if len(key) <= len(prev) else (prev, key)
        if len(short) >= 24 and short in long_ and (len(short) / max(len(long_), 1)) >= 0.92:
            return True
    return False


def canonical_line(text: str) -> str:
    text = normalize_text(text).lower()
    return re.sub(r"[\W_]+", "", text)


def is_duplicate_global(line: str, seen: list[str]) -> bool:
    key = canonical_line(line)
    return any(key == prev or key in prev or prev in key for prev in seen if prev)


def dedupe_drafts_across_slides(
    drafts: list[SlideDraft],
    template_slides: list[TemplateSlide],
    selected_sources: dict[int, list[str]],
) -> list[SlideDraft]:
    by_idx = {draft.slide_index: draft for draft in drafts}
    seen: list[str] = []
    out: list[SlideDraft] = []

    for slide in template_slides:
        draft = by_idx.get(slide.slide_index, SlideDraft(slide.slide_index, []))
        caps = slide_caps(slide.title, slide.has_table)
        target_max = caps["bullet_limit"]
        deduped: list[str] = []
        for line in draft.bullets:
            if is_duplicate_global(line, seen):
                continue
            deduped.append(line)
            seen.append(canonical_line(line))
            if len(deduped) >= target_max:
                break

        if len(deduped) < target_max:
            for src in selected_sources.get(slide.slide_index, []):
                candidate = detail_fallback_line(src, slide.title)
                if is_duplicate_global(candidate, seen):
                    continue
                deduped.append(candidate)
                seen.append(canonical_line(candidate))
                if len(deduped) >= target_max:
                    break

        out.append(SlideDraft(slide.slide_index, deduped))
    return out


def clean_metrics(raw_metrics: Any) -> dict[str, str]:
    metrics = {key: "-" for key in ALL_METRIC_LABELS}
    if isinstance(raw_metrics, dict):
        for key in metrics:
            if key in raw_metrics:
                metrics[key] = normalize_text(str(raw_metrics[key])) or "-"
    return metrics


def extract_numeric_metrics(paragraphs: list[dict[str, str]], metrics: dict[str, str]) -> dict[str, str]:
    text = "\n".join(p["text"] for p in paragraphs)

    def find(pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1) if m else None

    general = find(r"一般文件数量为\s*([0-9,]+)")
    legal = find(r"法律文件数量为\s*([0-9,]+)")
    patent_apply = find(r"(?:申请提案总数|专利申请提案统计[：:]?)\s*([0-9,]+)\s*件?")
    patent_survey = find(r"(?:专利调查统计[：:]?\s*(?:总计)?|调查统计[：:]?)\s*([0-9,]+)\s*件?")

    if general and metrics["一般文件用印"] == "-":
        metrics["一般文件用印"] = general
    if legal and metrics["法律文件用印"] == "-":
        metrics["法律文件用印"] = legal
    if patent_apply and metrics["BU10申请量"] == "-":
        metrics["BU10申请量"] = f"总计{patent_apply}(未拆分)"
    if patent_survey and metrics["专利调查量BU10"] == "-":
        metrics["专利调查量BU10"] = f"总计{patent_survey}(未拆分)"
    if patent_apply and metrics["其他知识产权申请"] == "-":
        metrics["其他知识产权申请"] = patent_apply
    if patent_apply:
        metrics["专利申请量"] = patent_apply
    if patent_survey:
        metrics["专利调查量"] = patent_survey
    return metrics


def extract_numeric_metrics_from_ocr(sections: list[dict[str, Any]], metrics: dict[str, str]) -> dict[str, str]:
    ocr_text = "\n".join(
        normalize_text(str(sec.get("ocr_text", "")))
        for sec in sections
        if normalize_text(str(sec.get("ocr_text", "")))
    )
    if not ocr_text:
        return metrics

    def find(pattern: str) -> str | None:
        m = re.search(pattern, ocr_text)
        return m.group(1) if m else None

    patent_apply = find(r"(?:专利)?申请(?:提案)?(?:统计)?[^0-9]{0,20}([0-9]{1,4})\s*件?")
    patent_survey = find(r"(?:专利)?调查(?:统计)?[^0-9]{0,20}([0-9]{1,4})\s*件?")
    if not patent_apply:
        patent_apply = find(r"([0-9]{1,4})\s*件[^。；\n]{0,20}(?:申请|提案)")
    if not patent_survey:
        patent_survey = find(r"([0-9]{1,4})\s*件[^。；\n]{0,20}(?:调查)")

    if patent_apply and (metrics.get("专利申请量", "-") in {"", "-"}):
        metrics["专利申请量"] = patent_apply
        if metrics.get("其他知识产权申请", "-") in {"", "-"}:
            metrics["其他知识产权申请"] = patent_apply
    if patent_survey and (metrics.get("专利调查量", "-") in {"", "-"}):
        metrics["专利调查量"] = patent_survey

    if patent_apply or patent_survey:
        log(f"OCR 数字提取成功: 专利申请量={patent_apply or '-'} 专利调查量={patent_survey or '-'}", level="INFO")
    metrics.update(extract_bu_metrics_from_ocr(sections))
    return metrics


def extract_bu_metrics_from_ocr(sections: list[dict[str, Any]]) -> dict[str, str]:
    apply_counts = {"BU10": 0, "BU11": 0, "BU16": 0}
    survey_counts = {"BU10": 0, "BU11": 0, "BU16": 0}

    for sec in sections:
        text = str(sec.get("ocr_text", ""))
        if not normalize_text(text):
            continue
        current_bu = ""
        for raw in text.splitlines():
            line = normalize_text(raw)
            if not line:
                continue
            bu_match = re.search(r"\((BU\s*1[016])\)", line, flags=re.IGNORECASE)
            if bu_match:
                current_bu = bu_match.group(1).replace(" ", "").upper()
                continue
            if "ZLSQ-TECH-" in line and current_bu in apply_counts:
                apply_counts[current_bu] += 1
                continue
            if "ZLDC-TECH-" in line and current_bu in survey_counts:
                survey_counts[current_bu] += 1
                continue

    metrics: dict[str, str] = {}
    for bu, count in apply_counts.items():
        if count:
            metrics[f"{bu}申请量"] = f"{count} (OCR)"
    for bu, count in survey_counts.items():
        if count:
            metrics[f"专利调查量{bu}"] = f"{count} (OCR)"
    return metrics


def fallback_drafts(template_slides: list[TemplateSlide], selected_sources: dict[int, list[str]]) -> list[SlideDraft]:
    log("使用规则模式生成细节要点")
    drafts: list[SlideDraft] = []
    for slide in template_slides:
        sources = selected_sources.get(slide.slide_index, [])
        caps = slide_caps(slide.title, slide.has_table)
        target_max = caps["bullet_limit"]
        target_min = caps["bullet_min"]
        if not sources:
            drafts.append(SlideDraft(slide.slide_index, []))
            continue
        lines: list[str] = []
        for src in sources:
            candidate = detail_fallback_line(src, slide.title)
            if candidate not in lines:
                lines.append(candidate)
            if len(lines) >= target_max:
                break
        while len(lines) < target_min:
            lines.append(short_line(f"{slide.title}重点事项跟进"))
        drafts.append(SlideDraft(slide.slide_index, lines[:target_max]))
    return drafts


def build_drafts_and_metrics(
    use_llm: bool,
    ollama_url: str,
    model: str,
    timeout_sec: int,
    retries: int,
    report_title: str,
    month_label: str,
    template_slides: list[TemplateSlide],
    doc_payload: dict[str, Any],
) -> tuple[list[SlideDraft], dict[str, str]]:
    selected_sources = select_source_lines(template_slides, doc_payload["sections"])
    fallback = fallback_drafts(template_slides, selected_sources)
    fallback_map = {draft.slide_index: draft for draft in fallback}

    if use_llm:
        try:
            prompt = build_rewrite_prompt(report_title, month_label, template_slides, selected_sources)
            raw = call_ollama_json(ollama_url, model, prompt, timeout_sec, retries)

            by_idx: dict[int, SlideDraft] = {}
            for row in raw.get("slides", []):
                try:
                    idx = int(row.get("slide_index"))
                except Exception:
                    continue
                bullets_raw = row.get("bullets", [])
                bullets: list[str] = []
                if isinstance(bullets_raw, list):
                    for item in bullets_raw:
                        line = short_line(clean_generated_line(str(item)))
                        if line and line not in bullets:
                            bullets.append(line)
                slide_meta = next((slide for slide in template_slides if slide.slide_index == idx), None)
                bullet_limit = slide_caps(slide_meta.title, slide_meta.has_table)["bullet_limit"] if slide_meta else 12
                by_idx[idx] = SlideDraft(idx, bullets[:bullet_limit])

            drafts: list[SlideDraft] = []
            for slide in template_slides:
                draft = by_idx.get(slide.slide_index, SlideDraft(slide.slide_index, []))
                caps = slide_caps(slide.title, slide.has_table)
                target_max = caps["bullet_limit"]
                target_min = caps["bullet_min"]
                sources = selected_sources.get(slide.slide_index, [])
                if not sources:
                    drafts.append(SlideDraft(slide.slide_index, []))
                    continue

                cleaned: list[str] = []
                for bullet in draft.bullets:
                    line = bullet
                    if not matches_title_profile(line, slide.title):
                        continue
                    if is_near_copy(line, sources):
                        line = detail_fallback_line(sources[0] if sources else line, slide.title)
                    if is_too_generic(line):
                        line = detail_fallback_line(sources[0] if sources else line, slide.title)
                    if not has_specific_signal(line, slide.title):
                        line = detail_fallback_line(sources[0] if sources else line, slide.title)
                    line = compress_for_ppt(line, slide.title)
                    if line not in cleaned:
                        cleaned.append(line)
                    if len(cleaned) >= target_max:
                        break

                if len(cleaned) < target_min:
                    for bullet in fallback_map[slide.slide_index].bullets:
                        if bullet not in cleaned:
                            cleaned.append(bullet)
                        if len(cleaned) >= target_max:
                            break

                drafts.append(SlideDraft(slide.slide_index, cleaned[:target_max]))

            metrics = clean_metrics(raw.get("metrics", {}))
            metrics = extract_numeric_metrics(doc_payload["paragraphs"], metrics)
            metrics = extract_numeric_metrics_from_ocr(doc_payload["sections"], metrics)
            return dedupe_drafts_across_slides(drafts, template_slides, selected_sources), metrics
        except Exception as exc:
            log(f"LLM 改写失败，退回规则模式: {exc}", level="WARN")

    metrics = clean_metrics({})
    metrics = extract_numeric_metrics(doc_payload["paragraphs"], metrics)
    metrics = extract_numeric_metrics_from_ocr(doc_payload["sections"], metrics)
    return dedupe_drafts_across_slides(fallback, template_slides, selected_sources), metrics
