from __future__ import annotations

import copy
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from doc_sanitizer import apply_mapping_to_file, read_mapping, scan_file
from doc_sanitizer.mapping import compact_entry_placeholders
from .defaults import DEFAULT_MODEL, DEFAULT_OLLAMA_URL


class SanitizeTabMixin:
    def _build_sanitize_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        main = ttk.PanedWindow(parent, orient="horizontal")
        main.grid(row=0, column=0, sticky="nsew")

        left_card = ttk.Frame(main, style="Card.TFrame", padding=18)
        right_card = ttk.Frame(main, style="Card.TFrame", padding=18)
        main.add(left_card, weight=4)
        main.add(right_card, weight=6)

        left_card.columnconfigure(0, weight=1)
        left_card.rowconfigure(2, weight=1)
        right_card.columnconfigure(0, weight=1)
        right_card.rowconfigure(0, weight=1)

        scan_group = ttk.LabelFrame(left_card, text="1. 识别候选", style="Section.TLabelframe", padding=14)
        scan_group.grid(row=0, column=0, sticky="ew")
        scan_group.columnconfigure(1, weight=1)
        self._add_path_row(scan_group, 0, "原始文件", self.sanitize_input_var, self._browse_sanitize_input)
        self._add_path_row(scan_group, 1, "脱敏输出", self.sanitize_output_var, self._browse_sanitize_output)
        self._add_path_row(scan_group, 2, "最终映射 JSON", self.sanitize_mapping_var, self._browse_sanitize_mapping)

        actions = ttk.Frame(scan_group, style="Card.TFrame")
        actions.grid(row=3, column=1, sticky="w", pady=(8, 0))
        self.initial_scan_button = ttk.Button(actions, text="识别候选映射", style="Primary.TButton", command=self.start_scan_mapping)
        self.initial_scan_button.pack(side="left")
        self.load_mapping_button = ttk.Button(actions, text="载入映射 JSON", style="Secondary.TButton", command=self.load_mapping_json)
        self.load_mapping_button.pack(side="left", padx=(8, 0))
        self.rescan_button = ttk.Button(actions, text="按当前映射继续识别", style="Secondary.TButton", command=self.rescan_mapping)
        self.rescan_button.pack(side="left", padx=(8, 0))
        self.apply_mapping_button = ttk.Button(actions, text="生成脱敏文档", style="Secondary.TButton", command=self.apply_current_mapping)
        self.apply_mapping_button.pack(side="left", padx=(8, 0))

        self.ai_notice_text = (
            "可以删除不需要的句子或段落，也可以改写内容。"
            "如果保留某个敏感信息，请保留对应占位符原样不变，例如 __COMPANY_001__ / __PERSON_003__。"
            "不要修改、拆分、翻译、加空格或改编号。"
            "如果整句被删除，其中的占位符也可一并删除；该项后续不会还原。"
            "如果要多轮重新识别，建议先批量添加你确定的重要项目或名称，再删除误识别项。"
        )
        ttk.Label(
            scan_group,
            text=self.ai_notice_text,
            style="Hint.TLabel",
            wraplength=480,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        strategy_group = ttk.LabelFrame(left_card, text="2. 识别策略", style="Section.TLabelframe", padding=14)
        strategy_group.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        strategy_group.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            strategy_group,
            text="启用本地模型辅助识别（默认）",
            variable=self.sanitize_use_llm_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(strategy_group, text="Ollama 地址", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(strategy_group, textvariable=self.ollama_url_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(strategy_group, text="模型", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=6)

        model_row = ttk.Frame(strategy_group, style="Card.TFrame")
        model_row.grid(row=2, column=1, sticky="ew", pady=6)
        model_row.columnconfigure(0, weight=1)
        self.sanitize_model_combo = ttk.Combobox(model_row, textvariable=self.model_var)
        self.sanitize_model_combo.grid(row=0, column=0, sticky="ew")
        ttk.Button(model_row, text="检测模型", style="Secondary.TButton", command=self.detect_models).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(
            strategy_group,
            text="建议流程：先识别候选 -> 审核映射 -> 再生成脱敏文档。",
            style="Hint.TLabel",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        log_group = ttk.LabelFrame(left_card, text="运行日志", style="Section.TLabelframe", padding=14)
        log_group.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        log_group.columnconfigure(0, weight=1)
        log_group.rowconfigure(0, weight=1)
        self.mask_log_text = self._create_log_widget(log_group)
        self.mask_log_text.grid(row=0, column=0, sticky="nsew")

        review_group = ttk.LabelFrame(right_card, text="3. 映射审核", style="Section.TLabelframe", padding=14)
        review_group.grid(row=0, column=0, sticky="nsew")
        review_group.columnconfigure(0, weight=1)
        review_group.rowconfigure(2, weight=1)

        summary_row = ttk.Frame(review_group, style="Card.TFrame")
        summary_row.grid(row=0, column=0, sticky="ew")
        summary_row.columnconfigure(0, weight=1)
        self.mapping_summary_var = tk.StringVar(value="尚未识别候选映射。")
        ttk.Label(summary_row, textvariable=self.mapping_summary_var, style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(summary_row, textvariable=self.sanitize_status_var, style="Status.TLabel").grid(row=0, column=1, sticky="e")

        search_row = ttk.Frame(review_group, style="Card.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="搜索", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_row, textvariable=self.mapping_search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        search_entry.bind("<KeyRelease>", self._schedule_mapping_search_refresh)
        ttk.Button(search_row, text="清空", style="Secondary.TButton", command=self.clear_mapping_search).grid(row=0, column=2)

        tree_shell = ttk.Frame(review_group, style="Card.TFrame")
        tree_shell.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        tree_shell.columnconfigure(0, weight=1)
        tree_shell.rowconfigure(0, weight=1)
        self.mapping_tree = ttk.Treeview(
            tree_shell,
            columns=("enabled", "category", "original", "placeholder", "source"),
            show="headings",
            height=18,
            style="Mapping.Treeview",
        )
        for key, label, width in [
            ("enabled", "启用", 60),
            ("category", "类别", 110),
            ("original", "敏感词", 430),
            ("placeholder", "替换为", 260),
            ("source", "来源", 90),
        ]:
            self.mapping_tree.heading(key, text=label)
            self.mapping_tree.column(key, width=width, anchor="w", stretch=True)
        scroll = ttk.Scrollbar(tree_shell, orient="vertical", command=self.mapping_tree.yview)
        xscroll = ttk.Scrollbar(tree_shell, orient="horizontal", command=self.mapping_tree.xview)
        self.mapping_tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.mapping_tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.mapping_tree.bind("<Double-1>", self._begin_tree_edit)
        self.mapping_tree.bind("<Delete>", lambda _event: self.remove_selected_mapping_entries())
        self.mapping_tree.bind("<space>", lambda _event: self.toggle_selected_mapping_entries())
        self.mapping_tree.bind("<Control-a>", self.select_all_visible_mapping_entries)
        self.mapping_tree.bind("<Control-A>", self.select_all_visible_mapping_entries)
        self.mapping_tree.bind("<Control-z>", self.undo_mapping_change)
        self.mapping_tree.bind("<Control-Z>", self.undo_mapping_change)

        tool_row = ttk.Frame(review_group, style="Card.TFrame")
        tool_row.grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Button(tool_row, text="撤销", style="Secondary.TButton", command=self.undo_mapping_change).pack(side="left")
        ttk.Button(tool_row, text="启用/禁用选中", style="Secondary.TButton", command=self.toggle_selected_mapping_entries).pack(side="left")
        ttk.Button(tool_row, text="删除选中", style="Secondary.TButton", command=self.remove_selected_mapping_entries).pack(side="left", padx=(8, 0))

        manual_row = ttk.Frame(review_group, style="Card.TFrame")
        manual_row.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        manual_row.columnconfigure(1, weight=1)
        manual_row.columnconfigure(3, weight=1)
        ttk.Label(manual_row, text="敏感词", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.manual_sensitive_entry = tk.Entry(manual_row, textvariable=self.manual_sensitive_var, font=("Microsoft YaHei UI", 10))
        self.manual_sensitive_entry.grid(row=0, column=1, sticky="ew", padx=(8, 16))
        ttk.Label(manual_row, text="替换为", style="Field.TLabel").grid(row=0, column=2, sticky="w")
        self.manual_placeholder_entry = tk.Entry(manual_row, textvariable=self.manual_placeholder_var, font=("Microsoft YaHei UI", 10))
        self.manual_placeholder_entry.grid(row=0, column=3, sticky="ew", padx=(8, 16))
        ttk.Button(manual_row, text="添加", style="Secondary.TButton", command=self.add_manual_mapping_entry).grid(row=0, column=4)

        batch_row = ttk.Frame(review_group, style="Card.TFrame")
        batch_row.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        batch_row.columnconfigure(0, weight=1)
        ttk.Label(batch_row, text="批量添加（支持 名称 / 类别+名称 / 名称+占位符）", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.batch_add_text = tk.Text(batch_row, height=4, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.batch_add_text.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(batch_row, text="批量添加", style="Secondary.TButton", command=self.add_manual_mapping_batch).grid(row=1, column=1, sticky="ne", padx=(10, 0))
        ttk.Label(
            review_group,
            text="支持双击表格直接编辑；生成脱敏文档前会自动整理占位符编号。生成后如继续修改映射，请放弃旧输出并重新生成脱敏文档。",
            style="Hint.TLabel",
        ).grid(row=6, column=0, sticky="w", pady=(8, 0))

    def _browse_sanitize_input(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("支持的文件", "*.doc *.docx *.ppt *.pptx"), ("Word 文档", "*.doc *.docx"), ("PPT 文档", "*.ppt *.pptx")]
        )
        if path:
            if not self._confirm_source_change_or_clear(path):
                return
            self.sanitize_input_var.set(path)
            self._set_default_sanitize_paths_for_source(path)

    def _browse_sanitize_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("支持的文件", "*.doc *.docx *.ppt *.pptx"), ("Word 文档", "*.doc *.docx"), ("PPT 文档", "*.ppt *.pptx")],
        )
        if path:
            self.sanitize_output_var.set(path)

    def _browse_sanitize_mapping(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            self.sanitize_mapping_var.set(path)

    def load_mapping_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            payload = read_mapping(Path(path))
        except Exception as exc:
            messagebox.showerror("载入失败", f"无法读取映射 JSON：{exc}")
            return
        self.current_mapping_data = payload
        self.scan_ready = True
        self.sanitize_mapping_var.set(path)
        source_file = str(payload.get("source_file", "")).strip()
        sanitized_file = str(payload.get("sanitized_file", "")).strip()
        self.mapping_applied = bool(sanitized_file)
        if source_file:
            self.sanitize_input_var.set(source_file)
        if sanitized_file:
            self.sanitize_output_var.set(sanitized_file)
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.mapping_summary_var.set(self._mapping_summary_text())
        self.sanitize_status_var.set("待确认")
        self._update_sanitize_action_states()
        self.log_queue.put(("sanitize", f"[INFO] 已载入映射 JSON: {path}"))

    def _validate_scan_inputs(self) -> bool:
        if not self.sanitize_input_var.get().strip():
            messagebox.showwarning("缺少参数", "请先选择原始文件。")
            return False
        if not self.sanitize_output_var.get().strip():
            messagebox.showwarning("缺少参数", "请先填写脱敏输出路径。")
            return False
        if not self.sanitize_mapping_var.get().strip():
            messagebox.showwarning("缺少参数", "请先填写最终映射 JSON 路径。")
            return False
        return True

    def _source_key(self, value: str) -> str:
        if not value.strip():
            return ""
        try:
            return str(Path(value).expanduser().resolve(strict=False)).casefold()
        except Exception:
            return value.strip().casefold()

    def _mapping_source_file(self) -> str:
        if not self.current_mapping_data:
            return ""
        return str(self.current_mapping_data.get("source_file", "")).strip()

    def _mapping_has_entries(self) -> bool:
        return bool(self._mapping_entries())

    def _set_default_sanitize_paths_for_source(self, source: str, force: bool = False) -> None:
        source_path = Path(source)
        stem = source_path.stem
        suffix = source_path.suffix.lower()
        if force or not self.sanitize_output_var.get():
            self.sanitize_output_var.set(str(source_path.with_name(f"{stem}_脱敏{suffix}")))
        if force or not self.sanitize_mapping_var.get():
            self.sanitize_mapping_var.set(str(source_path.with_name(f"{stem}_映射.json")))

    def _confirm_source_change_or_clear(self, new_source: str) -> bool:
        old_source = self._mapping_source_file()
        if not self._mapping_has_entries() or not old_source:
            return True
        if self._source_key(old_source) == self._source_key(new_source):
            return True
        choice = messagebox.askyesnocancel(
            "更换原始文件",
            "检测到你更换了原始文件。\n\n"
            "当前映射属于之前的文档，继续使用可能导致漏识别或还原错误。\n\n"
            "选择“是”：清空当前映射，并停在未识别状态。\n"
            "选择“否”：继续保留当前映射。\n"
            "选择“取消”：不更换文件。",
        )
        if choice is None:
            return False
        if choice:
            self._clear_mapping_for_new_source(new_source)
            return False
        self.log_queue.put(("sanitize", "[WARN] 已更换原始文件但继续沿用旧映射，请确认映射仍然适用于新文档。"))
        return True

    def _clear_mapping_for_new_source(self, new_source: str) -> None:
        self.current_mapping_data = None
        self.scan_ready = False
        self.mapping_applied = False
        self.mapping_undo_snapshot = None
        self.sanitize_input_var.set(new_source)
        self._set_default_sanitize_paths_for_source(new_source, force=True)
        self._refresh_mapping_tree()
        self.mapping_summary_var.set("尚未识别候选映射。")
        self.sanitize_status_var.set("等待识别")
        self._update_sanitize_action_states()
        self.log_queue.put(("sanitize", "[INFO] 已清空旧映射；请重新点击“识别候选映射”。"))

    def start_scan_mapping(self) -> None:
        if not self._validate_scan_inputs():
            return
        if not self._confirm_source_change_or_clear(self.sanitize_input_var.get().strip()):
            return
        params = self._scan_worker_params()
        self._start_worker("sanitize", self.sanitize_status_var, "[INFO] 开始识别候选映射...", lambda: self._scan_mapping_worker(params))

    def rescan_mapping(self) -> None:
        if not self.current_mapping_data:
            self.start_scan_mapping()
            return
        if not self._confirm_source_change_or_clear(self.sanitize_input_var.get().strip()):
            return
        params = self._scan_worker_params()
        self._start_worker("sanitize", self.sanitize_status_var, "[INFO] 按当前映射继续识别候选映射...", lambda: self._scan_mapping_worker(params))

    def _scan_worker_params(self) -> dict[str, object]:
        return {
            "input_path": Path(self.sanitize_input_var.get().strip()),
            "mapping_path": Path(self.sanitize_mapping_var.get().strip()),
            "use_llm_assist": bool(self.sanitize_use_llm_var.get()),
            "model": self.model_var.get().strip() or DEFAULT_MODEL,
            "ollama_url": self.ollama_url_var.get().strip() or DEFAULT_OLLAMA_URL,
            "timeout_sec": int(self.timeout_var.get().strip() or "120"),
            "retries": int(self.retries_var.get().strip() or "2"),
            "existing_payload": copy.deepcopy(self.current_mapping_data),
        }

    def _scan_mapping_worker(self, params: dict[str, object]) -> None:
        input_path = params["input_path"]
        existing_map_path = params["mapping_path"]
        assert isinstance(input_path, Path)
        assert isinstance(existing_map_path, Path)
        payload = scan_file(
            input_path=input_path,
            custom_terms=[],
            use_llm_assist=bool(params["use_llm_assist"]),
            model=str(params["model"]),
            ollama_url=str(params["ollama_url"]),
            timeout_sec=int(params["timeout_sec"]),
            retries=int(params["retries"]),
            existing_mapping_path=existing_map_path if existing_map_path.exists() else None,
            existing_payload=params["existing_payload"] if isinstance(params["existing_payload"], dict) else None,
        )
        self.root.after(0, lambda: self._after_scan_complete(payload))

    def _after_scan_complete(self, payload: dict[str, object]) -> None:
        self.current_mapping_data = payload
        self.scan_ready = True
        self.mapping_applied = False
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.sanitize_status_var.set("待确认")
        self.mapping_summary_var.set(self._mapping_summary_text())
        self._update_sanitize_action_states()
        self.log_queue.put(("sanitize", "[INFO] 候选映射已生成，请先审核，再决定是否生成脱敏文档。"))

    def apply_current_mapping(self) -> None:
        if not self._validate_scan_inputs():
            return
        if not self.current_mapping_data:
            messagebox.showwarning("无候选映射", "请先识别候选映射。")
            return
        self._compact_mapping_placeholders(log_changes=True)
        self._rebuild_mapping_metadata()
        params = self._apply_worker_params()
        self._start_worker("sanitize", self.sanitize_status_var, "[INFO] 开始生成脱敏文档...", lambda: self._apply_mapping_worker(params))

    def _apply_worker_params(self) -> dict[str, object]:
        assert self.current_mapping_data is not None
        return {
            "input_path": Path(self.sanitize_input_var.get().strip()),
            "output_path": self._unique_output_path(Path(self.sanitize_output_var.get().strip())),
            "mapping_path": self._unique_output_path(Path(self.sanitize_mapping_var.get().strip())),
            "payload": copy.deepcopy(self.current_mapping_data),
        }

    def _apply_mapping_worker(self, params: dict[str, object]) -> None:
        input_path = params["input_path"]
        output_path = params["output_path"]
        mapping_path = params["mapping_path"]
        payload = params["payload"]
        assert isinstance(input_path, Path)
        assert isinstance(output_path, Path)
        assert isinstance(mapping_path, Path)
        assert isinstance(payload, dict)
        payload["sanitized_file"] = str(output_path)
        apply_mapping_to_file(input_path, output_path, payload, mapping_path)
        self.root.after(0, lambda: self._after_apply_complete(output_path, mapping_path))

    def _after_apply_complete(self, output_path: Path, mapping_path: Path) -> None:
        self.sanitize_output_var.set(str(output_path))
        self.sanitize_mapping_var.set(str(mapping_path))
        self.sanitize_status_var.set("已生成")
        self.mapping_applied = True
        self.mapping_summary_var.set(self._mapping_summary_text())
        self._update_sanitize_action_states()
        self.log_queue.put(("sanitize", f"[INFO] 脱敏完成: {output_path}"))
        self.log_queue.put(("sanitize", f"[INFO] 映射文件已输出: {mapping_path}"))
        self.log_queue.put(("sanitize", f"[WARN] 外部 AI 使用提醒: {self.ai_notice_text}"))
        if not self.restore_mapping_var.get().strip():
            self.restore_mapping_var.set(str(mapping_path))

    def _mapping_entries(self) -> list[dict[str, object]]:
        if not self.current_mapping_data:
            return []
        entries = self.current_mapping_data.get("entries", [])
        return entries if isinstance(entries, list) else []

    def _mapping_summary_text(self) -> str:
        entries = self._mapping_entries()
        enabled = sum(1 for entry in entries if bool(entry.get("enabled", True)))
        categories: dict[str, int] = {}
        for entry in entries:
            if not bool(entry.get("enabled", True)):
                continue
            category = str(entry.get("category", "MANUAL"))
            categories[category] = categories.get(category, 0) + 1
        top = " / ".join(f"{k}:{v}" for k, v in list(categories.items())[:6]) if categories else "无"
        return f"当前候选 {len(entries)} 条，启用 {enabled} 条；分类概览：{top}"

    def _refresh_mapping_tree(self) -> None:
        self._close_tree_editor()
        self.mapping_tree.delete(*self.mapping_tree.get_children())
        search = self.mapping_search_var.get().strip().lower()
        for idx, entry in enumerate(self._mapping_entries()):
            hay = " ".join(
                [
                    str(entry.get("category", "")),
                    str(entry.get("original", "")),
                    str(entry.get("placeholder", "")),
                    str(entry.get("source", "")),
                ]
            ).lower()
            if search and search not in hay:
                continue
            self.mapping_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    "是" if bool(entry.get("enabled", True)) else "否",
                    str(entry.get("category", "")),
                    str(entry.get("original", "")),
                    str(entry.get("placeholder", "")),
                    str(entry.get("source", "")),
                ),
            )

    def clear_mapping_search(self) -> None:
        self._cancel_mapping_search_refresh()
        self.mapping_search_var.set("")
        self._refresh_mapping_tree()

    def _schedule_mapping_search_refresh(self, event=None):
        self._cancel_mapping_search_refresh()
        self.mapping_search_after_id = self.root.after(300, self._run_mapping_search_refresh)
        return None

    def _cancel_mapping_search_refresh(self) -> None:
        after_id = getattr(self, "mapping_search_after_id", None)
        if not after_id:
            return
        try:
            self.root.after_cancel(after_id)
        except Exception:
            pass
        self.mapping_search_after_id = None

    def _run_mapping_search_refresh(self) -> None:
        self.mapping_search_after_id = None
        self._refresh_mapping_tree()

    def _begin_tree_edit(self, event) -> None:
        item = self.mapping_tree.identify_row(event.y)
        column = self.mapping_tree.identify_column(event.x)
        if not item or column not in {"#2", "#3", "#4"}:
            return
        self._close_tree_editor()
        bbox = self.mapping_tree.bbox(item, column)
        if not bbox:
            return
        x, y, width, height = bbox
        values = list(self.mapping_tree.item(item, "values"))
        col_index = int(column[1:]) - 1
        current = values[col_index]
        editor = tk.Entry(self.mapping_tree, font=("Microsoft YaHei UI", 10))
        editor.insert(0, current)
        editor.select_range(0, tk.END)
        editor.focus_set()
        editor.place(x=x, y=y, width=width, height=height)
        editor.bind("<Return>", lambda _e: self._commit_tree_edit())
        editor.bind("<Escape>", lambda _e: self._close_tree_editor())
        editor.bind("<FocusOut>", lambda _e: self._commit_tree_edit())
        self.mapping_editor = editor
        self.mapping_editor_item = item
        self.mapping_editor_column = column

    def _commit_tree_edit(self) -> None:
        if not self.mapping_editor or self.mapping_editor_item is None or self.mapping_editor_column is None:
            return
        new_value = self.mapping_editor.get().strip()
        item_id = self.mapping_editor_item
        column = self.mapping_editor_column
        self._close_tree_editor()
        entries = self._mapping_entries()
        idx = int(item_id)
        if not (0 <= idx < len(entries)):
            return
        if not self._confirm_edit_after_apply():
            return
        self._save_mapping_undo_snapshot()
        entry = entries[idx]
        if column == "#2":
            category = (new_value or "MANUAL").upper()
            entry["category"] = category
            entry["placeholder"] = self._next_manual_placeholder(entries, category, exclude_index=idx)
        elif column == "#3":
            if new_value:
                entry["original"] = new_value
        elif column == "#4":
            if new_value:
                placeholder, category = self._normalize_placeholder_input(new_value, entries, str(entry.get("category", "MANUAL")), exclude_index=idx)
                entry["placeholder"] = placeholder
                entry["category"] = category
        self._compact_mapping_placeholders(log_changes=False)
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.mapping_summary_var.set(self._mapping_summary_text())
        self._update_sanitize_action_states()

    def _close_tree_editor(self) -> None:
        if self.mapping_editor is not None:
            try:
                self.mapping_editor.destroy()
            except Exception:
                pass
        self.mapping_editor = None
        self.mapping_editor_item = None
        self.mapping_editor_column = None

    def toggle_selected_mapping_entries(self) -> None:
        entries = self._mapping_entries()
        selected = self.mapping_tree.selection()
        if not entries or not selected:
            return
        if not self._confirm_edit_after_apply():
            return
        self._save_mapping_undo_snapshot()
        for item_id in selected:
            idx = int(item_id)
            if 0 <= idx < len(entries):
                entries[idx]["enabled"] = not bool(entries[idx].get("enabled", True))
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.mapping_summary_var.set(self._mapping_summary_text())
        self._update_sanitize_action_states()

    def remove_selected_mapping_entries(self) -> None:
        entries = self._mapping_entries()
        selected = sorted((int(item_id) for item_id in self.mapping_tree.selection()), reverse=True)
        if not entries or not selected:
            return
        if not self._confirm_edit_after_apply():
            return
        self._save_mapping_undo_snapshot()
        for idx in selected:
            if 0 <= idx < len(entries):
                entries.pop(idx)
        if not entries:
            self.current_mapping_data = None
            self.scan_ready = False
            self._refresh_mapping_tree()
            self.mapping_summary_var.set("尚未识别候选映射。")
            self.sanitize_status_var.set("等待识别")
            self._update_sanitize_action_states()
            return
        self._compact_mapping_placeholders(log_changes=True)
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.mapping_summary_var.set(self._mapping_summary_text())
        self._update_sanitize_action_states()

    def add_manual_mapping_entry(self) -> None:
        sensitive = self.manual_sensitive_var.get().strip()
        replacement = self.manual_placeholder_var.get().strip()
        if self.manual_sensitive_entry.cget("fg") == "#9aa8b6":
            sensitive = ""
        if self.manual_placeholder_entry.cget("fg") == "#9aa8b6":
            replacement = ""
        if not sensitive:
            messagebox.showwarning("缺少参数", "请先填写敏感词。")
            return
        if not self._confirm_edit_after_apply():
            return
        if not self.current_mapping_data:
            self.current_mapping_data = {"version": 2, "source_file": "", "sanitized_file": "", "entries": []}
        self._save_mapping_undo_snapshot()
        entries = self._mapping_entries()
        if any(str(item.get("original", "")).strip() == sensitive for item in entries):
            messagebox.showwarning("重复条目", "当前映射中已存在相同敏感词。")
            return
        category = self._infer_sensitive_category_from_text(sensitive, replacement)
        placeholder, _ = self._normalize_placeholder_input(replacement or "", entries, category)
        entries.append(
            {
                "placeholder": placeholder,
                "original": sensitive,
                "category": self._infer_manual_category(placeholder, sensitive),
                "enabled": True,
                "source": "manual",
            }
        )
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.mapping_summary_var.set(self._mapping_summary_text())
        self._update_sanitize_action_states()
        self.manual_sensitive_var.set("")
        self.manual_placeholder_var.set("")

    def add_manual_mapping_batch(self) -> None:
        raw = self.batch_add_text.get("1.0", tk.END)
        if self.batch_add_text.cget("fg") == "#9aa8b6":
            raw = ""
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            messagebox.showwarning("缺少参数", "请先输入要批量添加的敏感词。")
            return
        if not self._confirm_edit_after_apply():
            return
        if not self.current_mapping_data:
            self.current_mapping_data = {"version": 2, "source_file": "", "sanitized_file": "", "entries": []}
        self._save_mapping_undo_snapshot()
        entries = self._mapping_entries()
        added = 0
        for line in lines:
            sensitive, category_hint, placeholder_hint = self._parse_batch_line(line)
            if not sensitive:
                continue
            if any(str(item.get("original", "")).strip() == sensitive for item in entries):
                continue
            category = category_hint or self._infer_sensitive_category_from_text(sensitive, placeholder_hint)
            placeholder, _ = self._normalize_placeholder_input(placeholder_hint, entries, category)
            entries.append(
                {
                    "placeholder": placeholder,
                    "original": sensitive,
                    "category": self._infer_manual_category(placeholder, sensitive),
                    "enabled": True,
                    "source": "manual",
                }
            )
            added += 1
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.mapping_summary_var.set(self._mapping_summary_text())
        self._update_sanitize_action_states()
        self.batch_add_text.delete("1.0", tk.END)
        self.log_queue.put(("sanitize", f"[INFO] 批量添加敏感词：新增 {added} 条"))

    def _save_mapping_undo_snapshot(self) -> None:
        self.mapping_undo_snapshot = copy.deepcopy(self.current_mapping_data) if self.current_mapping_data else None

    def undo_mapping_change(self, event=None):
        if not self.mapping_undo_snapshot:
            self.log_queue.put(("sanitize", "[INFO] 当前没有可撤销的映射变更。"))
            return "break"
        self.current_mapping_data = copy.deepcopy(self.mapping_undo_snapshot)
        self.mapping_undo_snapshot = None
        self.scan_ready = True
        self.mapping_applied = bool(str(self.current_mapping_data.get("sanitized_file", "")).strip()) if self.current_mapping_data else False
        self._rebuild_mapping_metadata()
        self._refresh_mapping_tree()
        self.mapping_summary_var.set(self._mapping_summary_text())
        self.sanitize_status_var.set("已撤销，需重新生成")
        self._update_sanitize_action_states()
        self.log_queue.put(("sanitize", "[INFO] 已撤销最近一次映射变更。"))
        return "break"

    def select_all_visible_mapping_entries(self, event=None):
        children = self.mapping_tree.get_children()
        if children:
            self.mapping_tree.selection_set(children)
        return "break"

    def _compact_mapping_placeholders(self, log_changes: bool = False) -> dict[str, str]:
        entries = self._mapping_entries()
        if not entries:
            return {}
        changes = compact_entry_placeholders(entries)
        if log_changes and changes:
            preview = "；".join(f"{old}->{new}" for old, new in list(changes.items())[:12])
            suffix = f"，其余 {len(changes) - 12} 项" if len(changes) > 12 else ""
            self.log_queue.put(("sanitize", f"[INFO] 已整理映射编号 {len(changes)} 项：{preview}{suffix}"))
        return changes

    def _confirm_edit_after_apply(self) -> bool:
        if not getattr(self, "mapping_applied", False):
            return True
        confirmed = messagebox.askyesno(
            "已生成脱敏文档",
            "当前映射已用于生成脱敏文档。\n\n如果继续修改分类、编号、启用状态或条目，之前生成的脱敏文档和映射将不再可靠。\n请放弃之前生成的文件，并重新生成脱敏文档。\n\n是否继续编辑？",
        )
        if not confirmed:
            return False
        self.mapping_applied = False
        self.sanitize_status_var.set("已修改，需重新生成")
        self.log_queue.put(("sanitize", "[WARN] 已修改已生成映射，请重新生成脱敏文档；旧输出文件不应再用于外部 AI 或还原。"))
        return True

    def _parse_batch_line(self, line: str) -> tuple[str, str, str]:
        text = line.strip()
        if not text:
            return "", "", ""
        if "=>" in text:
            left, right = [part.strip() for part in text.split("=>", 1)]
            if left and right:
                if self._looks_like_category_token(left):
                    return right, left.upper(), ""
                return left, "", right
        if "->" in text:
            left, right = [part.strip() for part in text.split("->", 1)]
            if left and right:
                if self._looks_like_category_token(left):
                    return right, left.upper(), ""
                return left, "", right
        for sep in ("|", "\t", "：", ","):
            if sep in text:
                left, right = [part.strip() for part in text.split(sep, 1)]
                if not left or not right:
                    continue
                if self._looks_like_category_token(left):
                    return right, left.upper(), ""
                if self._looks_like_placeholder_token(right):
                    return left, "", right
                if self._looks_like_category_token(right):
                    return left, right.upper(), ""
        return text, "", ""

    @staticmethod
    def _looks_like_category_token(text: str) -> bool:
        return text.strip().upper() in {"COMPANY", "PERSON", "PROJECT", "CASE", "CODE", "CUSTOMER", "SUPPLIER", "TITLE", "MANUAL"}

    @staticmethod
    def _looks_like_placeholder_token(text: str) -> bool:
        return bool(re.fullmatch(r"(?:__)?[A-Za-z]+(?:_[0-9]{1,4})?(?:__)?", text.strip()))

    def _next_manual_placeholder(self, entries: list[dict[str, object]], category: str = "MANUAL", exclude_index: int | None = None) -> str:
        index = 1
        used = {
            str(item.get("placeholder", "")).strip().upper()
            for idx, item in enumerate(entries)
            if exclude_index is None or idx != exclude_index
        }
        while True:
            candidate = f"__{category.upper()}_{index:03d}__"
            if candidate.upper() not in used:
                return candidate
            index += 1

    def _normalize_placeholder_input(
        self,
        raw_value: str,
        entries: list[dict[str, object]],
        preferred_category: str,
        exclude_index: int | None = None,
    ) -> tuple[str, str]:
        raw = raw_value.strip()
        category = preferred_category.upper() or "MANUAL"
        if raw:
            cleaned = raw.upper().replace("-", "_").replace(" ", "_")
            cleaned = re.sub(r"_+", "_", cleaned).strip("_")
            match = re.fullmatch(r"(?:__)?([A-Z]+)(?:_)?(\d+)?(?:__)?", cleaned)
            if match:
                category = match.group(1).upper()
                if match.group(2):
                    desired = f"__{category}_{int(match.group(2)):03d}__"
                    used = {
                        str(item.get("placeholder", "")).strip().upper()
                        for idx, item in enumerate(entries)
                        if exclude_index is None or idx != exclude_index
                    }
                    if desired.upper() not in used:
                        return desired, category
                return self._tail_placeholder(entries, category, exclude_index=exclude_index), category
        return self._next_manual_placeholder(entries, category, exclude_index=exclude_index), category

    def _tail_placeholder(self, entries: list[dict[str, object]], category: str, exclude_index: int | None = None) -> str:
        category = category.upper()
        max_index = 0
        for idx, item in enumerate(entries):
            if exclude_index is not None and idx == exclude_index:
                continue
            placeholder = str(item.get("placeholder", "")).strip().upper()
            if not placeholder.startswith(f"__{category}_"):
                continue
            match = re.search(r"_(\d{1,5})__", placeholder)
            if match:
                max_index = max(max_index, int(match.group(1)))
        return f"__{category}_{max_index + 1:03d}__"

    @staticmethod
    def _infer_manual_category(placeholder: str, sensitive: str = "") -> str:
        text = placeholder.strip().upper()
        match = text.removeprefix("__")
        if match.endswith("__"):
            match = match[:-2]
        if "_" in match:
            return match.split("_", 1)[0]
        guess = SanitizeTabMixin._infer_sensitive_category_from_text(sensitive, placeholder)
        return guess or "MANUAL"

    @staticmethod
    def _infer_sensitive_category_from_text(sensitive: str, placeholder: str = "") -> str:
        text = (placeholder or "").strip().upper()
        if text.startswith("__"):
            inner = text.removeprefix("__")
            if inner.endswith("__"):
                inner = inner[:-2]
            if "_" in inner:
                return inner.split("_", 1)[0]
        raw = sensitive.strip()
        if re.search(r"(律师事务所|律所)$", raw):
            return "COMPANY"
        if re.search(r"(股份有限公司|有限责任公司|有限公司|分公司|集团|公司|科技|技术|电子|实业|贸易|国际)$", raw):
            return "COMPANY"
        if re.fullmatch(r"[A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,5}", raw):
            return "COMPANY"
        if re.fullmatch(r"(?:欧阳|司马|上官|诸葛|皇甫|尉迟|公孙|长孙|慕容|司徒|夏侯|东方|独孤|南宫|闻人|令狐|轩辕|赵|钱|孙|李|周|吴|郑|王|冯|陈|褚|卫|蒋|沈|韩|杨|朱|秦|尤|许|何|吕|施|张|孔|曹|严|华|金|魏|陶|姜|戚|谢|邹|喻|柏|窦|章|云|苏|潘|葛|范|彭|郎|鲁|韦|昌|马|苗|凤|花|方|俞|任|袁|柳|鲍|史|唐|费|廉|岑|薛|雷|贺|倪|汤|殷|罗|毕|郝|邬|安|常|乐|于|时|傅|皮|卞|齐|康|伍|余|元|卜|顾|孟|平|黄|和|穆|萧|尹)[一-龥某]{1,2}", raw):
            return "PERSON"
        if re.fullmatch(r"[A-Z]{2,}(?:[-_][A-Z0-9]+)+", raw):
            return "CODE"
        if "项目" in raw:
            return "PROJECT"
        return "MANUAL"

    def _rebuild_mapping_metadata(self) -> None:
        if not self.current_mapping_data:
            return
        entries = self._mapping_entries()
        replacements: dict[str, str] = {}
        categories: dict[str, str] = {}
        counts: dict[str, int] = {}
        for entry in entries:
            if not bool(entry.get("enabled", True)):
                continue
            placeholder = str(entry.get("placeholder", "")).strip()
            original = str(entry.get("original", "")).strip()
            category = str(entry.get("category", "MANUAL")).strip().upper()
            if not placeholder or not original:
                continue
            replacements[placeholder] = original
            categories[placeholder] = category
            counts[category] = counts.get(category, 0) + 1
        self.current_mapping_data["entries"] = entries
        self.current_mapping_data["replacements"] = replacements
        self.current_mapping_data["categories"] = categories
        self.current_mapping_data["counts"] = counts

    def _update_sanitize_action_states(self) -> None:
        entries = self._mapping_entries()
        valid_entries = [
            entry
            for entry in entries
            if str(entry.get("original", "")).strip() and str(entry.get("placeholder", "")).strip()
        ]
        has_mapping = len(valid_entries) > 0
        self.initial_scan_button.configure(state=("disabled" if has_mapping else "normal"))
        self.rescan_button.configure(state=("normal" if has_mapping else "disabled"))
        self.apply_mapping_button.configure(state=("normal" if has_mapping else "disabled"))
