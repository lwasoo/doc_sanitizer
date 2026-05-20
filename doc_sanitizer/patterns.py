"""Rule-based sensitive entity candidate extraction.

The regular expressions here provide a fast local first pass before optional LLM review.
Keep these patterns conservative because false positives become editable mapping entries.
"""

from __future__ import annotations

import re

from report_converter.common import normalize_text


COMPANY_SUFFIXES = [
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "科技有限公司",
    "技术有限公司",
    "电子有限公司",
    "实业有限公司",
    "贸易有限公司",
    "国际有限公司",
    "分公司",
    "有限公司",
    "律师事务所",
    "律所",
]
COMPANY_SUFFIX_PATTERN = "|".join(sorted((re.escape(x) for x in COMPANY_SUFFIXES), key=len, reverse=True))
GENERIC_COMPANY_VALUES = {
    "本公司",
    "该公司",
    "我司",
    "贵司",
    "公司",
    "集团",
    "集团公司",
    "某公司",
}
SENTENCE_LIKE_TOKENS = {"采取", "进行", "完成", "存在", "涉及", "相关", "推动", "处理", "开展", "公司应", "公司就"}
COMPANY_STOPWORDS = {
    "其中",
    "协助",
    "新增",
    "需要",
    "并约",
    "申请人",
    "被申请人",
    "妥善",
    "补充",
    "提交",
    "办理",
    "联系",
    "梳理",
    "平台",
    "竞争对手",
    "供应商",
    "客户",
    "终止与",
    "再向",
    "接单",
    "口头",
    "协调",
    "利用",
    "认为",
    "体检",
    "组织",
    "通过",
    "资料",
}

ENGLISH_GENERIC_TERMS = {
    "COMMITMENT PERIOD",
    "EFFECTIVE DATE",
    "STATE OF DELAWARE",
    "MEMORANDUM OF UNDERSTANDING",
    "GOVERNING LAW",
    "PURCHASE ORDER",
    "TERM AND TERMINATION",
    "CONFIDENTIAL INFORMATION",
}

GENERIC_ROLE_VALUES = {
    "客户",
    "供应商",
    "公司",
    "项目",
    "人员",
    "联系人",
    "申请人",
    "被申请人",
    "原告",
    "被告",
    "甲方",
    "乙方",
    "CUSTOMER",
    "SUPPLIER",
    "COMPANY",
    "PROJECT",
    "CONTACT",
    "CLIENT",
    "VENDOR",
}

PLACEHOLDER_PATTERNS: list[tuple[str, str]] = [
    ("COMPANY", rf"[\u4e00-\u9fffA-Za-z0-9（）()·&\-_]{{2,18}}(?:{COMPANY_SUFFIX_PATTERN})"),
    ("COMPANY", r"\b[A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,5}\s+(?:Legal|Technology|Technologies|Group|Holdings|Partners|Botts|Ltd|LTD|Inc|INC|LLC|PTE|Corp|Corporation|Company)\b"),
    ("COMPANY", r"[A-Za-z\u4e00-\u9fff]{2,24}(?:律师事务所|律所)"),
    ("TITLE", r"《[^》]{2,80}》"),
    ("AMOUNT", r"(?:人民币|美元|港币|欧元|日元)\s*\d[\d,]*(?:\.\d+)?\s*(?:亿元|万元|元|万美元|美元|港元|欧元|日元)?"),
    ("AMOUNT", r"\b(?:USD|RMB|CNY|HKD|EUR|JPY)\s*\d[\d,]*(?:\.\d+)?\b"),
    ("AMOUNT", r"[$￥]\s*\d[\d,]*(?:\.\d+)?\b"),
    ("ACCOUNT", r"\b\d{12,24}\b"),
    ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("PHONE", r"\b1[3-9]\d{9}\b"),
    ("CASE", r"\b(?:[A-Z]{2,}-)?(?:TECH-)?\d{3,}\b"),
    ("CODE", r"\b[A-Z]{2,}(?:[-_][A-Z0-9]{2,})+\b"),
]

CONTEXT_RULES: list[tuple[str, str]] = [
    ("PARTY", r"(?<=甲方[：:])[^，,。；;\n]{2,60}"),
    ("PARTY", r"(?<=乙方[：:])[^，,。；;\n]{2,60}"),
    ("PARTY", r"(?<=丙方[：:])[^，,。；;\n]{2,60}"),
    ("PROJECT", r"(?<=项目名称为)[^，,。；;\n]{2,80}"),
    ("PROJECT", r"(?<=项目名称[：:])[^，,。；;\n]{2,80}"),
    ("PROJECT", r"(?<=项目[：:])[^，,。；;\n]{2,80}"),
    ("CASE", r"(?<=案号[：:])[^，,。；;\n]{2,60}"),
    ("CASE", r"(?<=合同编号[：:])[^，,。；;\n]{2,60}"),
    ("SUPPLIER", r"(?<=供应商[：:])[^，,。；;\n]{2,80}"),
    ("CUSTOMER", r"(?<=客户[：:])[^，,。；;\n]{2,80}"),
]

PERSON_CONTEXT_PATTERNS: list[tuple[str, str]] = [
    (
        "PERSON",
        r"(?:申请人|被申请人|申请执行人|被申请执行人|原告|被告|仲裁员|代理人|联系人|员工|涉案人员)[：:\s]*"
        r"((?:欧阳|司马|上官|诸葛|皇甫|尉迟|公孙|长孙|慕容|司徒|夏侯|东方|独孤|南宫|闻人|令狐|轩辕|赵|钱|孙|李|周|吴|郑|王|冯|陈|褚|卫|蒋|沈|韩|杨|朱|秦|尤|许|何|吕|施|张|孔|曹|严|华|金|魏|陶|姜|戚|谢|邹|喻|柏|窦|章|云|苏|潘|葛|范|彭|郎|鲁|韦|昌|马|苗|凤|花|方|俞|任|袁|柳|鲍|史|唐|费|廉|岑|薛|雷|贺|倪|汤|滕|殷|罗|毕|郝|邬|安|常|乐|于|时|傅|皮|卞|齐|康|伍|余|元|卜|顾|孟|平|黄|和|穆|萧|尹)[一-龥某]{1,2})"
    ),
]


def match_candidates_in_text(text: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for category, pattern in PLACEHOLDER_PATTERNS:
        for match in re.finditer(pattern, text):
            value = clean_candidate_value(normalize_text(match.group(0)), category)
            if is_valid_candidate(value, category):
                out.append((category, value, "auto"))
    for category, pattern in CONTEXT_RULES:
        for match in re.finditer(pattern, text):
            value = clean_candidate_value(normalize_text(match.group(0)), category)
            if is_valid_candidate(value, category):
                out.append((category, value, "auto"))
    for category, pattern in PERSON_CONTEXT_PATTERNS:
        for match in re.finditer(pattern, text):
            value = clean_candidate_value(normalize_text(match.group(1)), category)
            if is_valid_candidate(value, category):
                out.append((category, value, "auto"))
    return out

def extract_contextual_candidates(text: str) -> list[tuple[str, str, str]]:
    text = normalize_text(text)
    out: list[tuple[str, str, str]] = []
    for chunk in re.split(r"[，,。；;：:\s]+", text):
        chunk = normalize_text(chunk)
        if 4 <= len(chunk) <= 12 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]{2,10}(?:集团|公司|科技|技术|电子|实业|贸易|国际)", chunk):
            chunk = clean_candidate_value(chunk, "COMPANY")
            if is_valid_candidate(chunk, "COMPANY"):
                out.append(("COMPANY", chunk, "auto"))
    if any(key in text for key in ["保密", "机密", "敏感", "涉美", "出口管制", "ECCN"]):
        for chunk in re.findall(r"[A-Z]{2,}(?:[-_][A-Z0-9]+)+", text):
            if is_valid_candidate(chunk, "CODE"):
                out.append(("CODE", chunk, "auto"))
    return out

def clean_candidate_value(value: str, category: str) -> str:
    value = normalize_text(value)
    if category == "PERSON" and len(value) >= 3 and value[-1] in {"非", "因", "与", "已", "将", "被", "系", "向", "于"}:
        value = value[:-1]
    if category == "CASE" and re.fullmatch(r"\d{4}", value):
        return ""
    return value

def is_amount_like(value: str) -> bool:
    value = normalize_text(value)
    if re.fullmatch(r"(?:第\s*)?\d+\s*(?:页|page|pages|%)", value, re.IGNORECASE):
        return False
    if re.search(r"(?:人民币|美元|港币|欧元|日元|USD|RMB|CNY|HKD|EUR|JPY|\$|￥)", value, re.IGNORECASE):
        return bool(re.search(r"\d", value))
    if re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:亿元|万元|元|万美元|美元|港元|欧元|日元|million|billion|thousand|yuan|dollars?)\b", value, re.IGNORECASE):
        return True
    if re.search(r"(?:金额|报价|付款|预算|合同价|交易金额|费用|价款|price|payment|budget|fee|cost|amount|value)", value, re.IGNORECASE):
        return bool(re.search(r"\d", value))
    return False

def is_valid_candidate(value: str, category: str) -> bool:
    value = normalize_text(value)
    if len(value) < 2:
        return False
    if value.upper() in GENERIC_ROLE_VALUES:
        return False
    if any(char in value for char in "\n\t"):
        return False
    if category == "AMOUNT":
        if not is_amount_like(value):
            return False
        if len(value) > 40:
            return False
        return True
    if sum(value.count(mark) for mark in "，,。；;！？!?") > 0:
        return False
    if category == "COMPANY":
        if value in GENERIC_COMPANY_VALUES:
            return False
        if value.upper() in ENGLISH_GENERIC_TERMS:
            return False
        if len(value) < 4 or len(value) > 24:
            return False
        if any(token in value for token in SENTENCE_LIKE_TOKENS):
            return False
        if any(token in value for token in COMPANY_STOPWORDS):
            return False
        if re.match(r"^(?:自\d{4}|其中|协助|新增|需要|并约|申请人|被申请人|妥善|补充|提交|办理|联系|梳理|平台)", value):
            return False
        if value.endswith("公司") and len(value) <= 4:
            return False
    if category == "TITLE" and len(value.strip("《》")) < 2:
        return False
    if category == "ACCOUNT" and value.startswith("2025") and len(value) <= 12:
        return False
    if category == "PERSON":
        if len(value) > 4:
            return False
        if any(token in value for token in ["公司", "集团", "部门", "项目"]):
            return False
    if category == "CASE":
        if value.isdigit():
            return False
        if len(value) < 4:
            return False
    if category == "CODE":
        if value.upper() in ENGLISH_GENERIC_TERMS:
            return False
        if " " in value and not re.search(r"[A-Z]{2,}(?:[-_][A-Z0-9]+)+", value):
            return False
    if category in {"PARTY", "PROJECT", "SUPPLIER", "CUSTOMER"} and len(value) > 40:
        return False
    if category in {"PROJECT", "SUPPLIER", "CUSTOMER"} and value.upper() in ENGLISH_GENERIC_TERMS:
        return False
    return True

