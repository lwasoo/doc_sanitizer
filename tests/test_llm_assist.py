"""Tests for LLM-assisted sensitive entity selection and prompt preparation.

The suite avoids live Ollama calls and focuses on deterministic pre-call filtering, chunking,
and cache behavior.
"""

from __future__ import annotations

import unittest

from doc_sanitizer.llm_assist import (
    build_llm_candidate_contexts,
    build_llm_candidate_prompt,
    chunk_texts_for_llm,
    choose_llm_prompt_language,
    count_texts_with_existing_terms,
    extract_candidates_from_llm_payload,
    select_texts_for_llm,
    stable_text_hash,
)
from doc_sanitizer.patterns import match_candidates_in_text


class LlmAssistPerformanceTests(unittest.TestCase):
    """Guard latency-oriented filtering before model calls are made."""

    def test_llm_text_selection_filters_low_signal_texts_and_caps_chunks(self) -> None:
        # 性能回归用例：全文 XML 扫描会带来很多低价值碎片，
        # 这些碎片不应全部送给 Ollama，避免模型调用次数暴涨。
        texts = [f"普通说明文字 {idx}" for idx in range(120)]
        texts.extend(
            [
                "客户：Acme Technology Co Ltd",
                "项目：Project Phoenix",
                "合同编号：TECH-2026-001",
            ]
        )

        selected = select_texts_for_llm(texts, max_texts=20)
        chunks = chunk_texts_for_llm(selected, max_chars=30, max_items=2, max_chunks=3)

        self.assertLess(len(selected), len(texts))
        self.assertIn("客户：Acme Technology Co Ltd", selected)
        self.assertLessEqual(len(chunks), 3)

    def test_llm_candidate_contexts_skip_existing_mapping_terms(self) -> None:
        # 性能/精度用例：已有映射中的原词不需要再次交给模型判断；
        # 模型只审核规则候选和上下文，减少重复调用。
        texts = [
            "客户 Acme Technology Co Ltd 与 Project Phoenix 沟通。",
            "客户 Acme Technology Co Ltd 与 Project Phoenix 沟通。",
        ]
        rule_candidates = [
            ("COMPANY", "Acme Technology Co Ltd", "auto"),
            ("PROJECT", "Project Phoenix", "auto"),
        ]

        contexts = build_llm_candidate_contexts(texts, rule_candidates, existing_terms={"Acme Technology Co Ltd"})

        self.assertEqual(len(contexts), 1)
        self.assertNotIn("Acme Technology Co Ltd", contexts[0].split("\n", 1)[0])
        self.assertIn("Project Phoenix", contexts[0])
        self.assertEqual(stable_text_hash(contexts[0]), stable_text_hash(contexts[0]))

    def test_llm_text_selection_keeps_free_extraction_for_new_entities(self) -> None:
        # 精度回归用例：初筛必须保留原文自由抽取能力；
        # 规则没抓到的新实体仍应能进入模型输入。
        selected = select_texts_for_llm(["新出现的 Alpha Beta Legal 需要模型自由识别。"], max_texts=10)

        self.assertIn("新出现的 Alpha Beta Legal 需要模型自由识别。", selected)

    def test_existing_mapping_terms_are_counted_for_gui_logging(self) -> None:
        # GUI 日志用例：继续识别时应能看到已有映射排除了多少相关段落。
        count = count_texts_with_existing_terms(
            ["Acme 已在映射里。", "Project Phoenix 是新项目。", "Acme 再次出现。"],
            {"Acme"},
        )

        self.assertEqual(count, 2)

    def test_english_prompt_is_used_for_english_heavy_text(self) -> None:
        # 英文模型/英文文档用英文指令，减少小模型跨语言理解损耗。
        chunk = [
            "Acme Technology Co Ltd signed Project Phoenix contract TECH-2026-001 with Beta Legal LLP.",
        ]

        language = choose_llm_prompt_language(chunk, model="phi4-mini:3.8b")
        prompt = build_llm_candidate_prompt(chunk, language=language)

        self.assertEqual(language, "en")
        self.assertIn("Identify sensitive entities", prompt)
        self.assertIn('"candidates"', prompt)

    def test_chinese_prompt_remains_default_for_qwen_chinese_text(self) -> None:
        # 中文文档和 Qwen 系列仍使用中文指令，保持现有主路径行为。
        chunk = ["客户：某某科技有限公司，项目：智慧园区平台，合同编号：ZH-2026-001。"]

        language = choose_llm_prompt_language(chunk, model="qwen2.5:7b-instruct-q4_K_M")
        prompt = build_llm_candidate_prompt(chunk, language=language)

        self.assertEqual(language, "zh")
        self.assertIn("请从下面文本中识别", prompt)
        self.assertIn('"candidates"', prompt)

    def test_prompt_language_preference_overrides_auto_detection(self) -> None:
        # UI 手动选择语言时，应允许中文文档用英文 prompt 做 A/B 测试。
        chunk = ["客户：某某科技有限公司，项目：智慧园区平台，合同编号：ZH-2026-001。"]

        self.assertEqual(choose_llm_prompt_language(chunk, model="phi4-mini:3.8b", preference="en"), "en")
        self.assertEqual(choose_llm_prompt_language(chunk, model="phi4-mini:3.8b", preference="zh"), "zh")

    def test_llm_payload_filters_sentence_like_and_generic_candidates(self) -> None:
        # 精度回归用例：小模型有时会返回整句或“客户/供应商”这类角色词，不能进入映射表。
        candidates = extract_candidates_from_llm_payload(
            {
                "candidates": [
                    {"text": "X项目的自动化设备供应商为集团内部供应商协讯自动化", "category": "SUPPLIER"},
                    {"text": "客户", "category": "CUSTOMER"},
                    {"text": "协讯自动化", "category": "SUPPLIER"},
                ]
            }
        )

        self.assertEqual(candidates, [("SUPPLIER", "协讯自动化", "llm")])

    def test_llm_payload_splits_merged_person_names(self) -> None:
        # 精度回归用例：模型把多个人名合并返回时，拆成独立候选，便于映射审核。
        candidates = extract_candidates_from_llm_payload(
            {"candidates": [{"text": "张三和李四", "category": "PERSON"}]}
        )

        self.assertEqual(candidates, [("PERSON", "张三", "llm"), ("PERSON", "李四", "llm")])

    def test_llm_payload_accepts_amounts_but_rejects_contextless_numbers(self) -> None:
        # 金额可以脱敏，但普通年份、页码、比例和无上下文纯数字不应进入映射表。
        candidates = extract_candidates_from_llm_payload(
            {
                "candidates": [
                    {"text": "人民币 1,200 万元", "category": "AMOUNT"},
                    {"text": "USD 500,000", "category": "AMOUNT"},
                    {"text": "2026", "category": "AMOUNT"},
                    {"text": "35%", "category": "AMOUNT"},
                    {"text": "第 12 页", "category": "AMOUNT"},
                ]
            }
        )

        self.assertEqual(
            candidates,
            [
                ("AMOUNT", "人民币 1,200 万元", "llm"),
                ("AMOUNT", "USD 500,000", "llm"),
            ],
        )

    def test_rule_extraction_catches_currency_prefixed_amounts(self) -> None:
        # 规则层应兜底抓住 MOU 里常见的 USD 金额，不依赖模型一定返回 AMOUNT。
        candidates = match_candidates_in_text(
            "Luxshare agrees to invest approximately USD 4,000,000. "
            "Orders shall total not less than USD 20,000,000."
        )

        self.assertIn(("AMOUNT", "USD 4,000,000", "auto"), candidates)
        self.assertIn(("AMOUNT", "USD 20,000,000", "auto"), candidates)

    def test_llm_payload_rejects_unknown_categories(self) -> None:
        # 模型可能创造 STATE_NAME 等类别；未列入映射类别的结果不应进入表格。
        candidates = extract_candidates_from_llm_payload(
            {"candidates": [{"text": "Delaware", "category": "STATE_NAME"}]}
        )

        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
