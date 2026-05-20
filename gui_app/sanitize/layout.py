"""Layout and path-selection helpers for the sanitize tab."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class SanitizeLayout:
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
        ttk.Label(strategy_group, text="Prompt 语言", style="Field.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        self.sanitize_prompt_language_combo = ttk.Combobox(
            strategy_group,
            textvariable=self.sanitize_prompt_language_var,
            values=("自动", "中文", "English"),
            state="readonly",
            width=14,
        )
        self.sanitize_prompt_language_combo.grid(row=3, column=1, sticky="w", pady=6)
        ttk.Label(
            strategy_group,
            text="建议流程：先识别候选 -> 审核映射 -> 再生成脱敏文档。",
            style="Hint.TLabel",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

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

    def _update_sanitize_action_states(self) -> None:
        entries = self._mapping_entries()
        valid_entries = [
            entry
            for entry in entries
            if entry.original and entry.placeholder
        ]
        has_mapping = len(valid_entries) > 0
        self.initial_scan_button.configure(state=("disabled" if has_mapping else "normal"))
        self.rescan_button.configure(state=("normal" if has_mapping else "disabled"))
        self.apply_mapping_button.configure(state=("normal" if has_mapping else "disabled"))


