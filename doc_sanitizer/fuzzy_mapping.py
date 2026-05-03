from __future__ import annotations

import json
import re
import string
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .mapping import ReplacementItem, mapping_entries, normalize_entries


PLACEHOLDER_RE = re.compile(r"_{0,2}([A-Za-z][A-Za-z0-9]*)(?:[\s_\-]+(\d{1,5}|MANUAL))_{0,2}")
COMPANY_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "集团股份有限公司",
    "集团有限公司",
    "有限公司",
    "责任公司",
    "控股集团",
    "控股",
    "集团",
    "公司",
    "技术",
    "科技",
    "corporation",
    "company",
    "limited",
    "incorporated",
    "ltd",
    "llc",
    "inc",
    "co",
)
PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation + "，。、《》？；：‘’“”（）【】「」『』、·—…￥")


@dataclass(frozen=True)
class EntityMatch:
    left: ReplacementItem
    right: ReplacementItem
    score: float
    reason: str


@dataclass(frozen=True)
class EntityGroup:
    items: list[ReplacementItem]
    score: float
    reason: str


@dataclass(frozen=True)
class PlaceholderRepair:
    token: str
    canonical: str
    score: float


@dataclass(frozen=True)
class PlaceholderParts:
    category: str
    index: str
    raw_index: str
    canonical: str


def payload_from_json_text(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是对象。")
    if "entries" in data:
        entries = data["entries"]
    else:
        replacements = data.get("replacements", {})
        categories = data.get("categories", {})
        if not isinstance(replacements, dict):
            raise ValueError("JSON 中没有 entries，也没有有效 replacements。")
        entries = [
            {
                "placeholder": placeholder,
                "original": original,
                "category": categories.get(placeholder, "AUTO") if isinstance(categories, dict) else "AUTO",
                "enabled": True,
                "source": "imported",
            }
            for placeholder, original in replacements.items()
        ]
    payload = {"version": 2, "entries": normalize_entries(entries if isinstance(entries, list) else [])}
    if not payload["entries"]:
        raise ValueError("JSON 中没有可用映射条目。")
    return payload


def enabled_items_from_payload(payload: dict[str, Any]) -> list[ReplacementItem]:
    return mapping_entries(payload, only_enabled=True)


def normalize_entity_name(value: str, category: str = "") -> str:
    text = unicodedata.normalize("NFKC", value).strip().lower()
    text = text.translate(PUNCT_TRANSLATION)
    text = re.sub(r"\s+", "", text)
    if category.upper() in {"COMPANY", "CUSTOMER", "SUPPLIER", "AUTO", "MANUAL"}:
        changed = True
        while changed:
            changed = False
            for suffix in COMPANY_SUFFIXES:
                if text.endswith(suffix) and len(text) > len(suffix) + 1:
                    text = text[: -len(suffix)]
                    changed = True
                    break
    return text


def entity_similarity(left: ReplacementItem, right: ReplacementItem) -> tuple[float, str]:
    if left.placeholder == right.placeholder:
        return 0.0, "same placeholder"
    if left.category != right.category and left.category not in {"AUTO", "MANUAL"} and right.category not in {"AUTO", "MANUAL"}:
        return 0.0, "category mismatch"

    a = normalize_entity_name(left.original, left.category)
    b = normalize_entity_name(right.original, right.category)
    if not a or not b:
        return 0.0, "empty"
    if a == b:
        return 0.98, "normalized exact match"

    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 2 and shorter in longer:
        ratio = len(shorter) / len(longer)
        return min(0.94, 0.76 + ratio * 0.18), "substring match"

    seq = SequenceMatcher(None, a, b).ratio()
    common = longest_common_substring_ratio(a, b)
    score = max(seq, common)
    if score >= 0.72:
        return score, "fuzzy text match"
    return score, "weak match"


def longest_common_substring_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    matcher = SequenceMatcher(None, left, right)
    match = max(matcher.get_matching_blocks(), key=lambda block: block.size, default=None)
    if not match or match.size == 0:
        return 0.0
    return (match.size * 2) / (len(left) + len(right))


def find_entity_matches(items: list[ReplacementItem], threshold: float = 0.70) -> list[EntityMatch]:
    matches: list[EntityMatch] = []
    for idx, left in enumerate(items):
        for right in items[idx + 1 :]:
            score, reason = entity_similarity(left, right)
            if score >= threshold:
                matches.append(EntityMatch(left=left, right=right, score=score, reason=reason))
    return sorted(matches, key=lambda item: item.score, reverse=True)


def group_entity_matches(items: list[ReplacementItem], threshold: float = 0.78) -> list[EntityGroup]:
    parent = list(range(len(items)))

    def find(idx: int) -> int:
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    pair_meta: dict[tuple[int, int], tuple[float, str]] = {}
    for i, left in enumerate(items):
        for j, right in enumerate(items[i + 1 :], start=i + 1):
            score, reason = entity_similarity(left, right)
            if score >= threshold:
                union(i, j)
                pair_meta[(i, j)] = (score, reason)

    groups_by_root: dict[int, list[int]] = {}
    for idx in range(len(items)):
        groups_by_root.setdefault(find(idx), []).append(idx)

    groups: list[EntityGroup] = []
    for indexes in groups_by_root.values():
        if len(indexes) < 2:
            continue
        scores = [
            pair_meta[(min(i, j), max(i, j))]
            for pos, i in enumerate(indexes)
            for j in indexes[pos + 1 :]
            if (min(i, j), max(i, j)) in pair_meta
        ]
        best_score, reason = max(scores, default=(threshold, "related names"))
        group_items = sorted((items[idx] for idx in indexes), key=lambda item: (-len(item.original), item.placeholder))
        groups.append(EntityGroup(items=group_items, score=best_score, reason=reason))
    return sorted(groups, key=lambda group: group.score, reverse=True)


def canonical_placeholder(value: str) -> str:
    parts = parse_placeholder_parts(value)
    return parts.canonical if parts else ""


def parse_placeholder_parts(value: str) -> PlaceholderParts | None:
    match = PLACEHOLDER_RE.fullmatch(unicodedata.normalize("NFKC", value).strip())
    if not match:
        return None
    category = match.group(1).upper()
    index = match.group(2)
    if not index:
        return PlaceholderParts(category=category, index="", raw_index="", canonical=f"__{category}__")
    if index.upper() == "MANUAL":
        return PlaceholderParts(category=category, index="MANUAL", raw_index="MANUAL", canonical=f"__{category}_MANUAL__")
    normalized_index = f"{int(index):03d}"
    return PlaceholderParts(category=category, index=normalized_index, raw_index=index, canonical=f"__{category}_{normalized_index}__")


def placeholder_category_score(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if len(left) >= 3 and right.endswith(left):
        return 0.92
    if len(right) >= 3 and left.endswith(right):
        return 0.92
    return SequenceMatcher(None, left, right).ratio()


def placeholder_index_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def placeholder_repair_score(token_parts: PlaceholderParts, target_parts: PlaceholderParts) -> float:
    category_score = placeholder_category_score(token_parts.category, target_parts.category)
    index_score = placeholder_index_score(token_parts.raw_index, target_parts.raw_index)
    if token_parts.index == target_parts.index:
        if category_score == 1.0:
            return 1.0
        if category_score >= 0.86:
            return 0.92
        if category_score >= 0.66:
            return 0.78
        return 0.0
    if category_score >= 0.86 and index_score >= 0.78:
        return min(0.89, 0.72 + index_score * 0.16)
    return 0.0


def suggest_placeholder_repairs(text: str, items: list[ReplacementItem], min_score: float = 0.70) -> list[PlaceholderRepair]:
    canonical_set = {item.placeholder.upper(): item.placeholder for item in items}
    target_parts = [
        (item.placeholder, parsed)
        for item in items
        for parsed in [parse_placeholder_parts(item.placeholder)]
        if parsed is not None
    ]
    repairs: list[PlaceholderRepair] = []
    for match in PLACEHOLDER_RE.finditer(text):
        token = match.group(0)
        token_parts = parse_placeholder_parts(token)
        if not token_parts:
            continue
        target = canonical_set.get(token_parts.canonical.upper())
        if target and token != target:
            repairs.append(PlaceholderRepair(token=token, canonical=target, score=1.0))
            continue
        best_target = ""
        best_score = 0.0
        for placeholder, parts in target_parts:
            score = placeholder_repair_score(token_parts, parts)
            if score > best_score:
                best_score = score
                best_target = placeholder
        if best_target and best_score >= min_score and token != best_target:
            repairs.append(PlaceholderRepair(token=token, canonical=best_target, score=best_score))
    return repairs


def repair_placeholder_text(
    text: str,
    items: list[ReplacementItem],
    min_score: float = 0.84,
    confirmed_repairs: dict[str, str] | None = None,
) -> str:
    updated = text
    if confirmed_repairs is None:
        repairs = {repair.token: repair.canonical for repair in suggest_placeholder_repairs(text, items, min_score=min_score)}
    else:
        repairs = confirmed_repairs
    updated = apply_placeholder_repairs(updated, repairs)
    return updated


def apply_placeholder_repairs(text: str, repairs: dict[str, str]) -> str:
    updated = text
    for token, canonical in sorted(repairs.items(), key=lambda item: len(item[0]), reverse=True):
        if token and canonical and token != canonical:
            updated = updated.replace(token, canonical)
    return updated


def build_external_ai_prompt(payload: dict[str, Any]) -> str:
    return build_external_ai_prompt_sections(payload)[0]


def build_external_ai_prompt_sections(payload: dict[str, Any]) -> tuple[str, str]:
    items = enabled_items_from_payload(payload)
    groups = group_entity_matches(items)

    prompt_lines = [
        "你将处理一份已经脱敏的文档。请严格遵守以下规则：",
        "",
        "1. 所有占位符必须原样保留，例如 __COMPANY_001__、__PERSON_003__。",
        "2. 不要翻译、改写、拆分、合并、加空格或重新编号任何占位符。",
        "3. 不要把占位符改成 CUSTOMER_001、Company 1、[客户] 等其他写法。",
        "4. 如果删除整句内容，其中的占位符可以一起删除；否则必须保留原占位符。",
        "5. 不要尝试推测、恢复或输出任何原始敏感词。",
        "",
    ]

    if groups:
        prompt_lines.extend(["同一对象提示：以下多个占位符可能指向同一个对象，改写时请保持指代关系一致。"])
        for idx, group in enumerate(groups, start=1):
            placeholders = " / ".join(item.placeholder for item in group.items)
            prompt_lines.append(f"- 组 {idx}: {placeholders}")
        prompt_lines.append("")

    prompt_lines.extend(
        [
            "最终交付要求：",
            "- 只返回处理后的正文或用户要求的格式。",
            "- 返回前自检：所有仍被保留的占位符必须与输入完全一致。",
        ]
    )

    audit_lines = [
        "内部审核说明（不要发给外部 AI）：",
        "以下信息用于解释为什么这些占位符被归为同一对象，包含原始敏感词。",
        "",
    ]
    if groups:
        audit_lines.append("同一对象归组理由：")
        for idx, group in enumerate(groups, start=1):
            placeholders = " / ".join(item.placeholder for item in group.items)
            originals = " / ".join(item.original for item in group.items)
            audit_lines.append(f"- 组 {idx}: {placeholders}")
            audit_lines.append(f"  原始名称线索：{originals}")
            audit_lines.append(f"  规则理由：{group.reason}，相似度 {group.score:.2f}")
    else:
        audit_lines.append("未发现高置信同一对象归组。")

    review_matches = [
        match
        for match in find_entity_matches(items, threshold=0.62)
        if all(match.left not in group.items or match.right not in group.items for group in groups)
    ][:20]
    if review_matches:
        audit_lines.extend(["", "仅供内部人工复核的相近对象候选："])
        for match in review_matches:
            audit_lines.append(
                f"- {match.left.placeholder}（{match.left.original}） <-> "
                f"{match.right.placeholder}（{match.right.original}），相似度 {match.score:.2f}，理由：{match.reason}"
            )

    return "\n".join(prompt_lines), "\n".join(audit_lines)
