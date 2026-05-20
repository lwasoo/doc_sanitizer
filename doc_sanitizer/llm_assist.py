"""Ollama-assisted sensitive entity discovery.

This module filters document text before model calls, builds strict JSON prompts, parses
model responses, and returns validated candidate entities for mapping merge.
"""

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
    prompt_language: str = "auto",
    rule_candidates: list[tuple[str, str, str]] | None = None,
    existing_terms: set[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Collect model-suggested sensitive entities after filtering low-signal and known text."""
    existing_terms = {normalize_text(term) for term in (existing_terms or set()) if normalize_text(term)}
    selected_texts = select_texts_for_llm(texts, max_texts=96, existing_terms=existing_terms)
    excluded_existing = count_texts_with_existing_terms(texts, existing_terms)
    text_languages = {text: choose_llm_prompt_language([text], model, prompt_language) for text in selected_texts}
    cached_payloads = [
        LLM_RESPONSE_CACHE[llm_cache_key(text, model, text_languages[text])]
        for text in selected_texts
        if llm_cache_key(text, model, text_languages[text]) in LLM_RESPONSE_CACHE
    ]
    llm_texts = [
        text
        for text in selected_texts
        if llm_cache_key(text, model, text_languages[text]) not in LLM_RESPONSE_CACHE
    ]
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
        chunk_prompt_language = choose_llm_prompt_language(chunk, model, prompt_language)
        prompt = build_llm_candidate_prompt(chunk, language=chunk_prompt_language)
        payload = call_ollama_candidate_json(
            ollama_url=ollama_url,
            model=model,
            prompt=prompt,
            prompt_language=chunk_prompt_language,
            timeout_sec=timeout_sec,
            retries=retries,
        )
        for context in chunk:
            LLM_RESPONSE_CACHE[llm_cache_key(context, model, chunk_prompt_language)] = payload
        candidates.extend(extract_candidates_from_llm_payload(payload))
    deduped: dict[str, tuple[str, str]] = {}
    for category, value, source in sorted(candidates, key=lambda item: len(item[1]), reverse=True):
        if normalize_text(value) in existing_terms:
            continue
        deduped.setdefault(normalize_text(value), (category, source))
    return [(category, original, source) for original, (category, source) in deduped.items()]


LLM_RESPONSE_CACHE: dict[str, dict[str, Any]] = {}
LLM_ALLOWED_CATEGORIES = {"COMPANY", "PERSON", "PROJECT", "CASE", "CODE", "CUSTOMER", "SUPPLIER", "TITLE", "AMOUNT"}


def stable_text_hash(text: str) -> str:
    """Hash normalized text so semantically identical snippets share cache entries."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def llm_cache_key(text: str, model: str, prompt_language: str) -> str:
    """Cache model responses without mixing different models or prompt languages."""
    normalized_model = normalize_text(model).lower()
    return hashlib.sha256(f"{prompt_language}\0{normalized_model}\0{normalize_text(text)}".encode("utf-8")).hexdigest()


def choose_llm_prompt_language(chunk: list[str], model: str = "", preference: str = "auto") -> str:
    """Choose Chinese or English instructions while keeping the output schema identical."""
    normalized_preference = preference.strip().lower()
    if normalized_preference in {"zh", "cn", "chinese", "中文"}:
        return "zh"
    if normalized_preference in {"en", "english", "英文"}:
        return "en"
    text = "\n".join(chunk)
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_letters = len(re.findall(r"[A-Za-z]", text))
    model_name = model.lower()
    english_first_models = ("phi", "llama", "gemma", "mistral", "mixtral")
    chinese_first_models = ("qwen", "yi", "deepseek")
    if english_letters >= max(40, chinese_chars * 3):
        return "en"
    if chinese_chars >= max(20, english_letters // 2):
        return "zh"
    if any(name in model_name for name in english_first_models):
        return "en"
    if any(name in model_name for name in chinese_first_models):
        return "zh"
    return "zh"


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
        if category not in LLM_ALLOWED_CATEGORIES:
            continue
        raw_original = clean_candidate_value(normalize_text(str(row.get("text", ""))), category)
        if is_sentence_like_llm_candidate(raw_original, category):
            continue
        for original in split_llm_candidate_value(raw_original, category):
            original = clean_candidate_value(original, category)
            if is_valid_candidate(original, category):
                candidates.append((category, original, "llm"))
    return candidates


def split_llm_candidate_value(value: str, category: str) -> list[str]:
    """Split model-merged short person names while leaving organization names intact."""
    value = normalize_text(value)
    if not value:
        return []
    if category != "PERSON":
        return [value]
    parts = [
        normalize_text(part)
        for part in re.split(r"\s*(?:和|与|及|、|,|，|/|&)\s*", value)
        if normalize_text(part)
    ]
    if len(parts) <= 1:
        return [value]
    return parts


def is_sentence_like_llm_candidate(value: str, category: str) -> bool:
    """Reject LLM outputs that copied a clause instead of returning a short entity."""
    value = normalize_text(value)
    if not value:
        return True
    if len(value) >= 18 and re.search(r"[的是为由将已把被对向与和及包括负责提供签署采购销售合作沟通]", value):
        return True
    if category in {"COMPANY", "PROJECT", "SUPPLIER", "CUSTOMER"} and re.search(
        r"(?:供应商为|客户为|项目为|公司为|主体为|负责人为|为集团|为公司|的自动化|的供应商|的客户|内部供应商)",
        value,
    ):
        return True
    if category == "PERSON" and re.search(r"(?:负责人|联系人|申请人|被申请人|原告|被告).{2,}", value):
        return True
    return False


def build_llm_candidate_contexts(
    texts: list[str],
    rule_candidates: list[tuple[str, str, str]],
    existing_terms: set[str],
    max_contexts: int = 80,
) -> list[str]:
    """Build compact rule-candidate contexts for a verification-style model prompt."""
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
    """Select high-signal snippets and skip text already covered by the current mapping."""
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
    """Rank snippets by cheap local signals before paying for model calls."""
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
    """Pack snippets into bounded prompts to keep Ollama latency and context drift controlled."""
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


def build_llm_candidate_prompt(chunk: list[str], candidate_mode: bool = False, language: str = "zh") -> str:
    """Build the extraction prompt; example JSON is intentionally separated from input text."""
    numbered = "\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(chunk))
    if candidate_mode:
        if language == "en":
            return f"""Review the following "candidate + context" items. Decide which candidates truly need sanitization, and add any clearly missing short entities from the same context. Output strict JSON only.

Rules:
1. Prefer real sensitive entities from the candidate list; do not return generic, descriptive, or non-sensitive terms.
2. Correct category when the candidate category is wrong.
3. Return only short entities that appear verbatim in the text. Do not rewrite, translate, infer, or invent.
4. If uncertain, do not return the item.
5. category must be one of: COMPANY, PERSON, PROJECT, CASE, CODE, CUSTOMER, SUPPLIER, TITLE, AMOUNT.
6. Do not return generic role labels, clauses, or multiple people merged into one string.
7. Numbers related to amounts, prices, payments, budgets, contract values, transaction values, costs, or fees may be returned as AMOUNT. Ordinary years, page numbers, indexes, percentages, and contextless pure numbers must not be returned.

Output format: {{"candidates":[{{"text":"<sensitive entity exactly as written in the source text>","category":"COMPANY"}}]}}

Items to review:
{numbered}
"""
        return f"""请审核下面的“候选 + 上下文”，判断哪些候选确实需要脱敏，并可补充同一上下文中明显遗漏的短实体。输出严格 JSON。

规则：
1. 优先返回候选中的真实敏感实体；不要返回不敏感、泛化或纯说明性词语。
2. 如果候选类别不准，可以修正 category。
3. 只返回文本中真实出现的短实体，不要改写，不要杜撰。
4. 如果不确定，不要返回。
5. category 只能是：COMPANY、PERSON、PROJECT、CASE、CODE、CUSTOMER、SUPPLIER、TITLE、AMOUNT。
6. 不要返回通用角色词、句子型候选，或把多个人名合并成一个候选。
7. 涉及金额、报价、付款、预算、合同价、交易金额、成本或费用的数字可以按 AMOUNT 返回；普通年份、页码、序号、比例和无上下文的纯数字不要返回。

输出格式：{{"candidates":[{{"text":"<原文中的敏感实体>","category":"COMPANY"}}]}}

待审核内容：
{numbered}
"""
    if language == "en":
        return f"""Identify sensitive entities that should be sanitized from the text below. Output strict JSON only.

Rules:
1. Extract only text that appears verbatim in the source. Do not rewrite, translate, infer, or invent entities.
2. Prioritize company names, English company names, law firms, people, project names, case numbers, contract numbers, customers, suppliers, codes, sensitive titles, and sensitive amounts.
3. Return short entities only. Do not return full sentences or explanatory phrases.
4. If uncertain, do not return the item.
5. category must be one of: COMPANY, PERSON, PROJECT, CASE, CODE, CUSTOMER, SUPPLIER, TITLE, AMOUNT.
6. Law firms, legal organizations, and named institutions should be returned as COMPANY.
7. Do not treat generic legal or contract terms as sensitive entities, such as Effective Date, Commitment Period, State of Delaware, Memorandum of Understanding.
8. Numbers related to amounts, prices, payments, budgets, contract values, transaction values, costs, or fees may be returned as AMOUNT.
9. Do not return ordinary years, page numbers, indexes, percentages, common legal phrases, state names, place names, or contextless pure numbers.

Output format:
{{"candidates":[{{"text":"<sensitive entity exactly as written in the source text>","category":"COMPANY"}}]}}

Important:
1. The output format above is only an example. It is not candidate content.
2. Never return example words, placeholders, or entities you invented.
3. Keep original spelling, capitalization, punctuation, and spacing exactly as they appear in the source text.

Text to inspect:
{numbered}
"""
    return f"""请从下面文本中识别需要脱敏的敏感实体，并输出严格 JSON。

规则：
1. 只抽取文本中真实出现的原文，不改写，不杜撰。
2. 优先识别：公司主体、英文公司名、律所、人名、项目名、案号、合同编号、客户、供应商、代码、标题、敏感金额。
3. 只返回短实体，不要返回整句描述。
4. 如果不确定，不要返回。
5. category 只能是：COMPANY、PERSON、PROJECT、CASE、CODE、CUSTOMER、SUPPLIER、TITLE、AMOUNT。
6. 律所、legal 或英文机构名称，也按 COMPANY 返回。
7. 不要把通用法律或合同术语当作敏感实体，例如 Effective Date、Commitment Period、State of Delaware、Memorandum of Understanding。
8. 涉及金额、报价、付款、预算、合同价、交易金额、成本或费用的数字可以按 AMOUNT 返回。
9. 普通年份、页码、序号、比例、常见法务短语、州名/地名和无上下文的纯数字不要返回。

输出格式：
{{"candidates":[{{"text":"<原文中的敏感实体>","category":"COMPANY"}}]}}

注意：
1. 上面只是格式示意，不是候选内容。
2. 绝对不要返回示例词、占位符或你自己编造的实体。

待识别文本：
{numbered}
"""


def extract_json_object(text: str) -> str:
    """Extract the first JSON object from model output that may include wrapper text."""
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
    prompt_language: str,
    timeout_sec: int,
    retries: int,
) -> dict[str, Any]:
    """Call Ollama using chat first and generate as a fallback, always requesting JSON."""
    if prompt_language == "en":
        system_prompt = "You are an enterprise document sanitization assistant. Output strict JSON only. Extract only clear sensitive entities and never return full sentences."
    else:
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
