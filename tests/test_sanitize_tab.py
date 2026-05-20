"""Tests for sanitize tab state transitions without launching the full GUI."""

from __future__ import annotations

import json
import tempfile
import unittest
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from doc_sanitizer.mapping import MappingPayload
from gui_app.sanitize.tab import SanitizeTabController


class SanitizeTabNumberingTests(unittest.TestCase):
    """Exercise mapping editor behavior through a lightweight tab harness."""

    def test_existing_manual_number_moves_entry_to_category_tail(self) -> None:
        tab = object.__new__(SanitizeTabController)
        entries = [
            {"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY"},
            {"placeholder": "__COMPANY_002__", "original": "B", "category": "COMPANY"},
            {"placeholder": "__COMPANY_003__", "original": "C", "category": "COMPANY"},
        ]

        placeholder, category = tab._normalize_placeholder_input("COMPANY_002", entries, "COMPANY", exclude_index=0)

        self.assertEqual(category, "COMPANY")
        self.assertEqual(placeholder, "__COMPANY_004__")

    def test_batch_line_accepts_fullwidth_and_similar_pipe_separators(self) -> None:
        tab = object.__new__(SanitizeTabController)

        self.assertEqual(tab._parse_batch_line("COMPANY\uff5cAcme"), ("Acme", "COMPANY", ""))
        self.assertEqual(tab._parse_batch_line("PERSON\u00a6Alice"), ("Alice", "PERSON", ""))
        self.assertEqual(tab._parse_batch_line("PROJECT\u2223Phoenix"), ("Phoenix", "PROJECT", ""))
        self.assertEqual(tab._parse_batch_line("com\uff5c23"), ("23", "COM", ""))

    def test_batch_line_treats_custom_left_token_as_category(self) -> None:
        tab = object.__new__(SanitizeTabController)

        sensitive, category, placeholder = tab._parse_batch_line("com|99")

        self.assertEqual((sensitive, category, placeholder), ("99", "COM", ""))

    def test_batch_line_uses_arrow_for_sensitive_term_to_placeholder(self) -> None:
        tab = object.__new__(SanitizeTabController)

        self.assertEqual(tab._parse_batch_line("Acme=>COMPANY_009"), ("Acme", "", "COMPANY_009"))
        self.assertEqual(tab._parse_batch_line("Acme=>__COMPANY_009__"), ("Acme", "", "__COMPANY_009__"))

    def test_edit_after_apply_requires_confirmation_and_marks_dirty(self) -> None:
        tab = object.__new__(SanitizeTabController)
        tab.mapping_applied = True
        tab.sanitize_status_var = tk.StringVar(master=tk.Tcl())
        rows: list[tuple[str, str]] = []
        tab.log_queue = type("FakeQueue", (), {"put": lambda _self, item: rows.append(item)})()

        with patch("gui_app.sanitize.table.messagebox.askyesno", return_value=True):
            allowed = tab._confirm_edit_after_apply()

        self.assertTrue(allowed)
        self.assertFalse(tab.mapping_applied)
        self.assertEqual(tab.sanitize_status_var.get(), "已修改，需重新生成")
        self.assertIn("重新生成脱敏文档", rows[0][1])

    def test_undo_mapping_change_restores_previous_snapshot(self) -> None:
        tab = object.__new__(SanitizeTabController)
        tab.current_mapping_data = {
            "entries": [
                {"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY", "enabled": True},
                {"placeholder": "__COMPANY_002__", "original": "B", "category": "COMPANY", "enabled": True},
            ]
        }
        tab.mapping_undo_snapshot = {
            "entries": [
                {"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY", "enabled": True}
            ]
        }
        tab.scan_ready = True
        tab.mapping_applied = True
        tab.sanitize_status_var = tk.StringVar(master=tk.Tcl())
        tab.mapping_summary_var = tk.StringVar(master=tk.Tcl())
        rows: list[tuple[str, str]] = []
        tab.log_queue = type("FakeQueue", (), {"put": lambda _self, item: rows.append(item)})()
        tab._refresh_mapping_tree = lambda: None
        tab._update_sanitize_action_states = lambda: None

        result = tab.undo_mapping_change()

        self.assertEqual(result, "break")
        self.assertEqual(len(tab.current_mapping_data["entries"]), 1)
        self.assertFalse(tab.mapping_applied)
        self.assertIsNone(tab.mapping_undo_snapshot)
        self.assertIn("已撤销", rows[0][1])

    def test_undo_mapping_change_restores_applied_state_from_snapshot(self) -> None:
        tab = object.__new__(SanitizeTabController)
        tab.current_mapping_data = {
            "sanitized_file": r"C:\source_脱敏.docx",
            "entries": [
                {"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY", "enabled": True},
                {"placeholder": "__COMPANY_002__", "original": "B", "category": "COMPANY", "enabled": True},
            ],
        }
        tab.mapping_undo_snapshot = {
            "sanitized_file": r"C:\source_脱敏.docx",
            "entries": [
                {"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY", "enabled": True}
            ],
        }
        tab.scan_ready = True
        tab.mapping_applied = False
        tab.sanitize_status_var = tk.StringVar(master=tk.Tcl())
        tab.mapping_summary_var = tk.StringVar(master=tk.Tcl())
        tab.log_queue = type("FakeQueue", (), {"put": lambda _self, item: None})()
        tab._refresh_mapping_tree = lambda: None
        tab._update_sanitize_action_states = lambda: None

        tab.undo_mapping_change()

        self.assertTrue(tab.mapping_applied)

    def test_select_all_visible_mapping_entries_returns_break(self) -> None:
        tab = object.__new__(SanitizeTabController)
        selected: list[tuple[str, ...]] = []
        tab.mapping_tree = type(
            "FakeTree",
            (),
            {
                "get_children": lambda _self: ("1", "2"),
                "selection_set": lambda _self, children: selected.append(tuple(children)),
            },
        )()

        result = tab.select_all_visible_mapping_entries()

        self.assertEqual(result, "break")
        self.assertEqual(selected, [("1", "2")])

    def test_mapping_search_refresh_is_debounced(self) -> None:
        tab = object.__new__(SanitizeTabController)
        calls: list[str] = []
        canceled: list[str] = []

        class FakeRoot:
            def after(self, delay: int, callback):
                calls.append(f"{delay}:{callback.__name__}")
                return f"after-{len(calls)}"

            def after_cancel(self, after_id: str) -> None:
                canceled.append(after_id)

        tab.root = FakeRoot()
        tab.mapping_search_after_id = None
        tab._refresh_mapping_tree = lambda: calls.append("refresh")

        tab._schedule_mapping_search_refresh()
        tab._schedule_mapping_search_refresh()
        tab._run_mapping_search_refresh()

        self.assertEqual(calls, ["300:_run_mapping_search_refresh", "300:_run_mapping_search_refresh", "refresh"])
        self.assertEqual(canceled, ["after-1"])
        self.assertIsNone(tab.mapping_search_after_id)

    def test_clear_mapping_search_cancels_pending_debounce_and_refreshes_now(self) -> None:
        tab = object.__new__(SanitizeTabController)
        canceled: list[str] = []
        refreshed: list[str] = []
        tab.root = type("FakeRoot", (), {"after_cancel": lambda _self, after_id: canceled.append(after_id)})()
        tab.mapping_search_after_id = "after-1"
        tab.mapping_search_var = tk.StringVar(master=tk.Tcl(), value="company")
        tab._refresh_mapping_tree = lambda: refreshed.append("refresh")

        tab.clear_mapping_search()

        self.assertEqual(canceled, ["after-1"])
        self.assertEqual(tab.mapping_search_var.get(), "")
        self.assertEqual(refreshed, ["refresh"])
        self.assertIsNone(tab.mapping_search_after_id)

    def test_manual_entry_can_start_from_empty_mapping(self) -> None:
        tab = object.__new__(SanitizeTabController)
        root = tk.Tcl()
        tab.current_mapping_data = None
        tab.mapping_applied = False
        tab.manual_sensitive_var = tk.StringVar(master=root, value="Acme")
        tab.manual_placeholder_var = tk.StringVar(master=root, value="")
        tab.manual_sensitive_entry = type("FakeEntry", (), {"cget": lambda _self, _key: "#111111"})()
        tab.manual_placeholder_entry = type("FakeEntry", (), {"cget": lambda _self, _key: "#111111"})()
        tab.mapping_summary_var = tk.StringVar(master=root)
        tab._refresh_mapping_tree = lambda: None
        tab._update_sanitize_action_states = lambda: None

        tab.add_manual_mapping_entry()

        self.assertIsInstance(tab.current_mapping_data, MappingPayload)
        self.assertEqual(len(tab.current_mapping_data.entries), 1)
        self.assertEqual(tab.current_mapping_data.entries[0].original, "Acme")
        self.assertEqual(tab.current_mapping_data.entries[0].placeholder, "__COMPANY_001__")

    def test_source_change_can_clear_mapping_without_continuing_scan(self) -> None:
        tab = object.__new__(SanitizeTabController)
        tab.current_mapping_data = {
            "source_file": r"C:\old.docx",
            "entries": [{"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY"}],
        }
        tab.scan_ready = True
        tab.mapping_applied = True
        tab.mapping_undo_snapshot = {"entries": []}
        tab.sanitize_input_var = tk.StringVar(master=tk.Tcl(), value=r"C:\old.docx")
        tab.sanitize_output_var = tk.StringVar(master=tk.Tcl(), value=r"C:\old_脱敏.docx")
        tab.sanitize_mapping_var = tk.StringVar(master=tk.Tcl(), value=r"C:\old_映射.json")
        tab.sanitize_status_var = tk.StringVar(master=tk.Tcl())
        tab.mapping_summary_var = tk.StringVar(master=tk.Tcl())
        rows: list[tuple[str, str]] = []
        tab.log_queue = type("FakeQueue", (), {"put": lambda _self, item: rows.append(item)})()
        tab._refresh_mapping_tree = lambda: None
        tab._update_sanitize_action_states = lambda: None

        with patch("gui_app.sanitize.layout.messagebox.askyesnocancel", return_value=True):
            should_continue = tab._confirm_source_change_or_clear(r"C:\new.docx")

        self.assertFalse(should_continue)
        self.assertIsNone(tab.current_mapping_data)
        self.assertFalse(tab.scan_ready)
        self.assertFalse(tab.mapping_applied)
        self.assertIsNone(tab.mapping_undo_snapshot)
        self.assertEqual(tab.sanitize_input_var.get(), r"C:\new.docx")
        self.assertEqual(tab.sanitize_output_var.get(), r"C:\new_脱敏.docx")
        self.assertEqual(tab.sanitize_mapping_var.get(), r"C:\new_映射.json")
        self.assertIn("清空", rows[0][1])

    def test_source_change_can_keep_mapping_and_log_warning(self) -> None:
        tab = object.__new__(SanitizeTabController)
        tab.current_mapping_data = {
            "source_file": r"C:\old.docx",
            "entries": [{"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY"}],
        }
        rows: list[tuple[str, str]] = []
        tab.log_queue = type("FakeQueue", (), {"put": lambda _self, item: rows.append(item)})()

        with patch("gui_app.sanitize.layout.messagebox.askyesnocancel", return_value=False):
            should_continue = tab._confirm_source_change_or_clear(r"C:\new.docx")

        self.assertTrue(should_continue)
        self.assertIsNotNone(tab.current_mapping_data)
        self.assertIn("[WARN]", rows[0][1])

    def test_load_mapping_json_with_sanitized_file_marks_mapping_applied(self) -> None:
        tab = object.__new__(SanitizeTabController)
        root = tk.Tcl()
        tab.sanitize_mapping_var = tk.StringVar(master=root)
        tab.sanitize_input_var = tk.StringVar(master=root)
        tab.sanitize_output_var = tk.StringVar(master=root)
        tab.sanitize_status_var = tk.StringVar(master=root)
        tab.mapping_summary_var = tk.StringVar(master=root)
        rows: list[tuple[str, str]] = []
        tab.log_queue = type("FakeQueue", (), {"put": lambda _self, item: rows.append(item)})()
        tab._refresh_mapping_tree = lambda: None
        tab._update_sanitize_action_states = lambda: None

        with tempfile.TemporaryDirectory() as tmpdir:
            mapping_path = Path(tmpdir) / "mapping.json"
            payload = {
                "source_file": r"C:\source.docx",
                "sanitized_file": r"C:\source_脱敏.docx",
                "entries": [
                    {"placeholder": "__COMPANY_001__", "original": "A", "category": "COMPANY", "enabled": True}
                ],
            }
            mapping_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with patch("gui_app.sanitize.actions.filedialog.askopenfilename", return_value=str(mapping_path)):
                tab.load_mapping_json()

        self.assertTrue(tab.mapping_applied)
        self.assertEqual(tab.sanitize_output_var.get(), r"C:\source_脱敏.docx")

    def test_apply_mapping_worker_accepts_mapping_payload_dataclass(self) -> None:
        tab = object.__new__(SanitizeTabController)
        completed: list[tuple[Path, Path]] = []
        tab.root = type("FakeRoot", (), {"after": lambda _self, _delay, callback: callback()})()
        tab._after_apply_complete = lambda output_path, mapping_path: completed.append((output_path, mapping_path))
        payload = MappingPayload(
            entries=[
                {"placeholder": "__COMPANY_001__", "original": "Acme", "category": "COMPANY", "enabled": True}
            ]
        )
        params = {
            "input_path": Path("input.docx"),
            "output_path": Path("output.docx"),
            "mapping_path": Path("mapping.json"),
            "payload": payload,
        }

        with patch("gui_app.sanitize.actions.apply_mapping_to_file") as apply_mock:
            tab._apply_mapping_worker(params)

        self.assertEqual(payload.sanitized_file, "output.docx")
        apply_mock.assert_called_once()
        self.assertEqual(completed, [(Path("output.docx"), Path("mapping.json"))])

    def test_scan_mapping_worker_passes_mapping_payload_dataclass(self) -> None:
        tab = object.__new__(SanitizeTabController)
        completed: list[MappingPayload] = []
        existing = MappingPayload(
            entries=[
                {"placeholder": "__COMPANY_001__", "original": "Acme", "category": "COMPANY", "enabled": True}
            ]
        )
        result = MappingPayload(entries=existing.entries)
        tab.root = type("FakeRoot", (), {"after": lambda _self, _delay, callback: callback()})()
        tab._after_scan_complete = lambda payload: completed.append(payload)
        params = {
            "input_path": Path("input.docx"),
            "mapping_path": Path("mapping.json"),
            "use_llm_assist": False,
            "model": "model",
            "ollama_url": "http://127.0.0.1:11434",
            "timeout_sec": 120,
            "retries": 2,
            "prompt_language": "en",
            "existing_payload": existing,
        }

        with patch("gui_app.sanitize.actions.scan_file", return_value=result) as scan_mock:
            tab._scan_mapping_worker(params)

        self.assertIs(scan_mock.call_args.kwargs["existing_payload"], existing)
        self.assertEqual(scan_mock.call_args.kwargs["prompt_language"], "en")
        self.assertEqual(completed, [result])


if __name__ == "__main__":
    unittest.main()
