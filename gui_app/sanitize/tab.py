"""GUI tab for scanning, reviewing, and applying document sanitization mappings."""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from doc_sanitizer.mapping import MappingPayload

from .actions import SanitizeActions
from .layout import SanitizeLayout
from .table import SanitizeMappingTable


class SanitizeTabController(SanitizeLayout, SanitizeActions, SanitizeMappingTable):
    """Own sanitize-tab state and expose only explicit integration points."""

    def __init__(
        self,
        parent: ttk.Frame,
        *,
        root: tk.Tk,
        log_queue: queue.Queue[tuple[str, str]],
        model_var: tk.StringVar,
        ollama_url_var: tk.StringVar,
        timeout_var: tk.StringVar,
        retries_var: tk.StringVar,
        start_worker: Callable[[str, tk.StringVar, str, Callable[[], None]], None],
        unique_output_path: Callable[[Path], Path],
        add_path_row: Callable[[ttk.Frame, int, str, tk.StringVar, Callable[[], None]], None],
        create_log_widget: Callable[[ttk.Frame], ScrolledText],
        detect_models: Callable[[], None],
        set_restore_mapping_path_if_empty: Callable[[Path], None],
        install_entry_placeholder: Callable[[tk.Entry, tk.StringVar, str], None],
        install_text_placeholder: Callable[[tk.Text, str], None],
    ) -> None:
        self.root = root
        self.log_queue = log_queue
        self.model_var = model_var
        self.ollama_url_var = ollama_url_var
        self.timeout_var = timeout_var
        self.retries_var = retries_var
        self._start_worker_callback = start_worker
        self._unique_output_path_callback = unique_output_path
        self._add_path_row_callback = add_path_row
        self._create_log_widget_callback = create_log_widget
        self.detect_models = detect_models
        self._set_restore_mapping_path_if_empty_callback = set_restore_mapping_path_if_empty
        self._install_entry_placeholder_callback = install_entry_placeholder
        self._install_text_placeholder_callback = install_text_placeholder

        self.sanitize_input_var = tk.StringVar()
        self.sanitize_output_var = tk.StringVar()
        self.sanitize_mapping_var = tk.StringVar()
        self.sanitize_status_var = tk.StringVar(value="等待识别")
        self.sanitize_use_llm_var = tk.BooleanVar(value=True)
        self.sanitize_prompt_language_var = tk.StringVar(value="自动")
        self.manual_sensitive_var = tk.StringVar()
        self.manual_placeholder_var = tk.StringVar()
        self.mapping_search_var = tk.StringVar()
        self.current_mapping_data: MappingPayload | None = None
        self.scan_ready = False
        self.mapping_applied = False
        self.mapping_undo_snapshot: MappingPayload | None = None
        self.mapping_search_after_id: str | None = None
        self.mapping_editor: tk.Entry | None = None
        self.mapping_editor_item: str | None = None
        self.mapping_editor_column: str | None = None
        self.batch_placeholder_text = "示例：\nCOMPANY|Google LLC\nPERSON|张三\n示例项目=>__PROJECT_008__\n某某科技有限公司"
        self.manual_sensitive_placeholder = "输入敏感词，例如：Google LLC"
        self.manual_placeholder_hint = "可留空；也可写 COMPANY 或 __COMPANY_010__"

        self._build_sanitize_tab(parent)
        self._setup_placeholder_hints()
        self._update_sanitize_action_states()

    def _start_worker(self, target: str, status_var: tk.StringVar, start_msg: str, func: Callable[[], None]) -> None:
        self._start_worker_callback(target, status_var, start_msg, func)

    def _unique_output_path(self, path: Path) -> Path:
        return self._unique_output_path_callback(path)

    def _add_path_row(self, frame: ttk.Frame, row: int, label: str, var: tk.StringVar, browse_cmd: Callable[[], None]) -> None:
        self._add_path_row_callback(frame, row, label, var, browse_cmd)

    def _create_log_widget(self, parent: ttk.Frame) -> ScrolledText:
        return self._create_log_widget_callback(parent)

    def _set_restore_mapping_path_if_empty(self, mapping_path: Path) -> None:
        self._set_restore_mapping_path_if_empty_callback(mapping_path)

    def _setup_placeholder_hints(self) -> None:
        self._install_entry_placeholder_callback(self.manual_sensitive_entry, self.manual_sensitive_var, self.manual_sensitive_placeholder)
        self._install_entry_placeholder_callback(self.manual_placeholder_entry, self.manual_placeholder_var, self.manual_placeholder_hint)
        self._install_text_placeholder_callback(self.batch_add_text, self.batch_placeholder_text)


