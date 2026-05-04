from __future__ import annotations

import unittest

from doc_sanitizer.mapping import compact_entry_placeholders, refresh_payload_metadata


class MappingNumberingTests(unittest.TestCase):
    def test_compact_placeholders_fills_deleted_index_gap(self) -> None:
        entries = [
            {"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY", "enabled": True},
            {"placeholder": "__COMPANY_003__", "original": "C", "category": "COMPANY", "enabled": True},
            {"placeholder": "__COMPANY_004__", "original": "D", "category": "COMPANY", "enabled": True},
        ]

        changes = compact_entry_placeholders(entries)

        self.assertEqual(changes["__COMPANY_003__"], "__COMPANY_002__")
        self.assertEqual(changes["__COMPANY_004__"], "__COMPANY_003__")
        self.assertEqual([entry["placeholder"] for entry in entries], ["__COMPANY_001__", "__COMPANY_002__", "__COMPANY_003__"])

    def test_compact_placeholders_moves_large_manual_index_to_tail(self) -> None:
        entries = [
            {"placeholder": f"__PROJECT_{index:03d}__", "original": f"P{index}", "category": "PROJECT", "enabled": True}
            for index in range(1, 23)
        ]
        entries.append({"placeholder": "__PROJECT_034__", "original": "Manual large index", "category": "PROJECT", "enabled": True})

        compact_entry_placeholders(entries)

        self.assertEqual(entries[-1]["placeholder"], "__PROJECT_023__")

    def test_compact_placeholders_prioritizes_enabled_entries(self) -> None:
        entries = [
            {"placeholder": "__COMPANY_001__", "original": "Disabled", "category": "COMPANY", "enabled": False},
            {"placeholder": "__COMPANY_002__", "original": "Enabled A", "category": "COMPANY", "enabled": True},
            {"placeholder": "__COMPANY_004__", "original": "Enabled B", "category": "COMPANY", "enabled": True},
        ]

        compact_entry_placeholders(entries)

        enabled_placeholders = [entry["placeholder"] for entry in entries if entry["enabled"]]
        disabled_placeholders = [entry["placeholder"] for entry in entries if not entry["enabled"]]
        self.assertEqual(enabled_placeholders, ["__COMPANY_001__", "__COMPANY_002__"])
        self.assertEqual(disabled_placeholders, ["__COMPANY_003__"])

    def test_refresh_payload_metadata_uses_compacted_placeholders(self) -> None:
        payload = {
            "entries": [
                {"placeholder": "__CODE_001__", "original": "A", "category": "CODE", "enabled": True},
                {"placeholder": "__CODE_003__", "original": "B", "category": "CODE", "enabled": True},
            ]
        }

        compact_entry_placeholders(payload["entries"])
        refresh_payload_metadata(payload)

        self.assertEqual(set(payload["replacements"]), {"__CODE_001__", "__CODE_002__"})


if __name__ == "__main__":
    unittest.main()
