from __future__ import annotations

import json
import re
import hashlib
from typing import Any
import urllib.error
import urllib.request

from report_converter.common import log, normalize_text
from .patterns import clean_candidate_value, extract_contextual_candidates, is_valid_candidate, match_candidates_in_text

def collect_llm_candidates(
    texts: list[str],
    model: str,
    ollama_url: str,
    timeout_sec: int,
    retries: int,
    rule_candidates: list[tuple[str, str, str]] | None = None,
    existing_terms: set[str] | None = None,
) -> list[tuple[str, str, str]]:
    existing_terms = {normalize_text(term) for term in (existing_terms or set()) if normalize_text(term)}
    selected_texts = select_texts_for_llm(texts, max_texts=96, existing_terms=existing_terms)
    excluded_existing = count_texts_with_existing_terms(texts, existing_terms)
    cached_payloads = [LLM_RESPONSE_CACHE[stable_text_hash(text)] for text in selected_texts if stable_text_hash(text) in LLM_RESPONSE_CACHE]
    llm_texts = [text for text in selected_texts if stable_text_hash(text) not in LLM_RESPONSE_CACHE]
    chunks = chunk_texts_for_llm(llm_texts, max_chars=1800, max_items=16, max_chunks=12)
    log(
        "AI 辅助识别准备: "
        f"全文 {len(texts)} 段，规则候选 {len(rule_candidates or [])} 条，"
        f"送模型 {len(llm_texts)} 段，缓存命中 {len(cached_payloads)} 段，"
        f"排除已有映射相关段 {excluded_existing} 段，模型分段 {len(chunks)} 段"
    )
    candidates: list[tuple[str, str, str]] = []
    for payload in cached_payloads:
        candidates.extend(extract_candidates_from_llm_payload(payload))
    for idx, chunk in enumerate(chunks, start=1):
        log(f"AI 辅助识别分段 {idx}/{len(chunks)}")
        prompt = build_llm_candidate_prompt(chunk)
        payload = call_ollama_candidate_json(
            ollama_url=ollama_url,
            model=model,
            prompt=prompt,
            timeout_sec=timeout_sec,
            retries=retries,
        )
        for context in chunk:
            LLM_RESPONSE_CACHE[stable_text_hash(context)] = payload
        candidates.extend(extract_candidates_from_llm_payload(payload))
    deduped: dict[str, tuple[str, str]] = {}
    for category, value, source in sorted(candidates, key=lambda item: len(item[1]), reverse=True):
        if normalize_text(value) in existing_terms:
            continue
        deduped.setdefault(normalize_text(value), (category, source))
    return [(category, original, source) for original, (category, source) in deduped.items()]


LLM_RESPONSE_CACHE: dict[str, dict[str, Any]] = {}


def stable_text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def count_texts_with_existing_terms(texts: list[str], existing_terms: set[str]) -> int:
    if not existing_terms:
        return 0
    return sum(1 for text in texts if any(term and term in normalize_text(text) for term in existing_terms))


def extract_candidates_from_llm_payload(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    for row in payload.get("candidates", []):
        if not isinstance(row, dict):
            continue
        category = normalize_text(str(row.get("category", "")).upper()) or "MANUAL"
        original = clean_candidate_value(normalize_text(str(row.get("text", ""))), category)
        if is_valid_candidate(original, category):
            candidates.append((category, original, "llm"))
    return candidates


def build_llm_candidate_contexts(
    texts: list[str],
    rule_candidates: list[tuple[str, str, str]],
    existing_terms: set[str],
    max_contexts: int = 80,
) -> list[str]:
    terms = [
        (category, normalize_text(value))
        for category, value, _source in rule_candidates
        if normalize_text(value) and normalize_text(value) not in existing_terms
    ]
    contexts: list[str] = []
    seen: set[str] = set()
    for text in texts:
        normalized = normalize_text(text)
        if not normalized:
            continue
        matched = [(category, value) for category, value in terms if value and value in normalized]
        if not matched:
            continue
        candidate_part = "；".join(f"{category}|{value}" for category, value in matched[:8])
        context = f"候选：{candidate_part}\n上下文：{normalized[:500]}"
        key = stable_text_hash(context)
        if key in seen:
            continue
        seen.add(key)
        contexts.append(context)
        if len(contexts) >= max_contexts:
            break
    return contexts


def select_texts_for_llm(texts: list[str], max_texts: int = 72, existing_terms: set[str] | None = None) -> list[str]:
    existing_terms = existing_terms or set()
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(texts):
        text = normalize_text(raw)
        if len(text) < 4 or text in seen:
            continue
        if any(term and term in text for term in existing_terms):
            continue
        seen.add(text)
        score = llm_text_score(text)
        if score > 0:
            scored.append((score, -index, text))
    if not scored:
        return list(seen)[:max_texts]
    return [text for _score, _index, text in sorted(scored, reverse=True)[:max_texts]]


def llm_text_score(text: str) -> int:
    score = 0
    if match_candidates_in_text(text) or extract_contextual_candidates(text):
        score += 5
    sensitive_markers = [
        "公司",
        "客户",
        "供应商",
        "项目",
        "合同",
        "案号",
        "申请人",
        "被申请人",
        "联系人",
        "律所",
        "律师事务所",
        "保密",
        "涉美",
        "出口管制",
    ]
    score += sum(1 for marker in sensitive_markers if marker in text)
    if any(char.isdigit() for char in text):
        score += 1
    if any(char.isupper() for char in text):
        score += 1
    if len(text) > 160:
        score -= 1
    return score


def chunk_texts_for_llm(texts: list[str], max_chars: int = 1800, max_items: int = 16, max_chunks: int = 12) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for text in texts:
        line = normalize_text(text)
        if not line:
            continue
        line_len = len(line) + 1
        if current and (current_len + line_len > max_chars or len(current) >= max_items):
            chunks.append(current)
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append(current)
    return chunks[:max_chunks]

def build_llm_candidate_prompt(chunk: list[str], candidate_mode: bool = False) -> str:
    numbered = "\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(chunk))
    if candidate_mode:
        return f"""请审核下面的“候选 + 上下文”，判断哪些候选确实需要脱敏，并可补充同一上下文中明显遗漏的短实体。输出严格 JSON。

规则：
1. 优先返回候选中的真实敏感实体；不要返回不敏感、泛化或纯说明性词语。
2. 如果候选类别不准，可以修正 category。
3. 只返回文本中真实出现的短实体，不要改写，不要杜撰。
4. 如果不确定，不要返回。
5. category 只能是：COMPANY、PERSON、PROJECT、CASE、CODE、CUSTOMER、SUPPLIER、TITLE。

输出格式：{{"candidates":[{{"text":"<原文中的敏感实体>","category":"COMPANY"}}]}}

待审核内容：
{numbered}
"""
    return f"""请从下面文本中识别需要脱敏的敏感实体，并输出严格 JSON。

规则：
1. 只抽取文本中真实出现的原文，不改写，不杜撰。
2. 优先识别：公司主体、英文公司名、律所、人名、项目名、案号、合同编号、客户、供应商、代码、标题。
3. 只返回短实体，不要返回整句描述。
4. 如果不确定，不要返回。
5. category 只能是：COMPANY、PERSON、PROJECT、CASE、CODE、CUSTOMER、SUPPLIER、TITLE。
6. 像 Baker Botts、TransPerfect Legal、贝克博茨律所 这类律所或英文机构，也按 COMPANY 返回。
7. 不要把通用法律或合同术语当作敏感实体，例如 Effective Date、Commitment Period、State of Delaware、Memorandum of Understanding。
8. 纯数字、常见法务短语、州名/地名如果没有明确敏感含义，不要返回。

输出格式：
{{"candidates":[{{"text":"<原文中的敏感实体>","category":"COMPANY"}}]}}

注意：
1. 上面只是格式示意，不是候选内容。
2. 绝对不要返回示例词、占位符或你自己编造的实体。

待识别文本：
{numbered}
"""

def extract_json_object(text: str) -> str:
    payload = text.strip()
    if payload.startswith("{") and payload.endswith("}"):
        return payload
    match = re.search(r"\{[\s\S]*\}", payload)
    if match:
        return match.group(0)
    raise ValueError("LLM 返回中未找到 JSON。")

def call_ollama_candidate_json(
    ollama_url: str,
    model: str,
    prompt: str,
    timeout_sec: int,
    retries: int,
) -> dict[str, Any]:
    system_prompt = "你是企业文档脱敏助手。只能输出严格 JSON，只抽取明确敏感实体，禁止返回整句。"
    endpoints = [
        ("chat", f"{ollama_url.rstrip('/')}/api/chat"),
        ("generate", f"{ollama_url.rstrip('/')}/api/generate"),
    ]
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        for kind, url in endpoints:
            try:
                log(f"调用 Ollama 脱敏辅助 ({kind}) 第 {attempt} 次: {url}")
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
                log(f"Ollama 脱敏辅助失败: {exc}", level="WARN")
                continue
    if last_error is None:
        raise RuntimeError("Ollama 脱敏辅助失败。")
    raise RuntimeError(f"Ollama 脱敏辅助失败: {last_error}") from last_error

