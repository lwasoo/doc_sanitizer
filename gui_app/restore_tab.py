from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from doc_sanitizer import read_mapping, restore_file
from doc_sanitizer.document_io import collect_texts_for_path
from doc_sanitizer.fuzzy_mapping import PlaceholderRepair, suggest_placeholder_repairs
from doc_sanitizer.mapping import mapping_entries


class RestoreTabMixin:
    def _build_restore_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        main = ttk.PanedWindow(parent, orient="horizontal")
        main.grid(row=0, column=0, sticky="nsew")

        left_card = ttk.Frame(main, style="Card.TFrame", padding=18)
        right_card = ttk.Frame(main, style="Card.TFrame", padding=18)
        main.add(left_card, weight=5)
        main.add(right_card, weight=4)
        left_card.columnconfigure(0, weight=1)
        right_card.columnconfigure(0, weight=1)
        right_card.rowconfigure(1, weight=1)

        restore_group = ttk.LabelFrame(left_card, text="1. 还原文件", style="Section.TLabelframe", padding=14)
        restore_group.grid(row=0, column=0, sticky="ew")
        restore_group.columnconfigure(1, weight=1)
        self._add_path_row(restore_group, 0, "AI 修改后文件", self.restore_input_var, self._browse_restore_input)
        self._add_path_row(restore_group, 1, "映射 JSON", self.restore_mapping_var, self._browse_restore_mapping)
        self._add_path_row(restore_group, 2, "还原输出", self.restore_output_var, self._browse_restore_output)

        action_row = ttk.Frame(restore_group, style="Card.TFrame")
        action_row.grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Button(action_row, text="开始还原", style="Primary.TButton", command=self.start_restore).pack(side="left")
        ttk.Label(action_row, textvariable=self.restore_status_var, style="Status.TLabel").pack(side="left", padx=(12, 0))

        help_group = ttk.LabelFrame(left_card, text="2. 使用说明", style="Section.TLabelframe", padding=14)
        help_group.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        ttk.Label(
            help_group,
            text=(
                "还原会按映射 JSON 中的占位符，把当前文件里仍然保留的占位符替换回原始敏感信息。"
                "如果外部 AI 把占位符改成相似但不完全一致的写法，开始前会弹出确认列表。"
                "如果整段内容已被删除，对应敏感信息不会被重新补回。"
            ),
            style="Hint.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(right_card, text="运行日志", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.restore_log_text = self._create_log_widget(right_card)
        self.restore_log_text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _browse_restore_input(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("支持的文件", "*.doc *.docx *.ppt *.pptx"), ("Word 文档", "*.doc *.docx"), ("PPT 文档", "*.ppt *.pptx")]
        )
        if path:
            self.restore_input_var.set(path)
            if not self.restore_output_var.get():
                suffix = Path(path).suffix.lower()
                self.restore_output_var.set(str(Path(path).with_name(f"{Path(path).stem}_还原{suffix}")))

    def _browse_restore_mapping(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.restore_mapping_var.set(path)

    def _browse_restore_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("支持的文件", "*.doc *.docx *.ppt *.pptx"), ("Word 文档", "*.doc *.docx"), ("PPT 文档", "*.ppt *.pptx")],
        )
        if path:
            self.restore_output_var.set(path)

    def _validate_restore_inputs(self) -> bool:
        if not self.restore_input_var.get().strip() or not self.restore_mapping_var.get().strip() or not self.restore_output_var.get().strip():
            messagebox.showwarning("缺少参数", "请填写还原所需的文件 / 映射 / 输出路径。")
            return False
        return True

    def start_restore(self) -> None:
        if not self._validate_restore_inputs():
            return
        input_path = Path(self.restore_input_var.get().strip())
        mapping_path = Path(self.restore_mapping_var.get().strip())
        try:
            repair_plan = self._confirm_placeholder_repairs(input_path, mapping_path)
        except Exception as exc:
            messagebox.showerror("占位符检查失败", f"无法检查相似占位符：{exc}")
            return
        if repair_plan is None:
            self.restore_status_var.set("已取消")
            return
        placeholder_repairs, auto_repairs, confirmed_repairs = repair_plan
        params = {
            "input_path": input_path,
            "mapping_path": mapping_path,
            "output_path": self._unique_output_path(Path(self.restore_output_var.get().strip())),
            "placeholder_repairs": placeholder_repairs,
            "auto_repairs": auto_repairs,
            "confirmed_repairs": confirmed_repairs,
        }
        self._start_worker("restore", self.restore_status_var, "[INFO] 开始还原文档...", lambda: self._restore_worker(params))

    def _restore_worker(self, params: dict[str, object]) -> None:
        input_path = params["input_path"]
        mapping_path = params["mapping_path"]
        output_path = params["output_path"]
        placeholder_repairs = params["placeholder_repairs"]
        auto_repairs = params["auto_repairs"]
        confirmed_repairs = params["confirmed_repairs"]
        assert isinstance(input_path, Path)
        assert isinstance(mapping_path, Path)
        assert isinstance(output_path, Path)
        assert isinstance(placeholder_repairs, dict)
        assert isinstance(auto_repairs, dict)
        assert isinstance(confirmed_repairs, dict)
        restore_file(
            input_path=input_path,
            output_path=output_path,
            mapping_path=mapping_path,
            placeholder_repairs=placeholder_repairs,
        )
        payload = read_mapping(mapping_path)
        originals_by_placeholder = {
            str(entry.get("placeholder", "")): str(entry.get("original", ""))
            for entry in payload.get("entries", [])
            if isinstance(entry, dict)
        }
        self.log_queue.put(("restore", f"[INFO] 还原输入: {input_path}"))
        self.log_queue.put(("restore", f"[INFO] 使用映射: {mapping_path}"))
        for token, canonical in auto_repairs.items():
            original = originals_by_placeholder.get(canonical, "")
            self.log_queue.put(("restore", f"[INFO] 自动修复相似占位符: {token} -> {canonical} -> {original}"))
        for token, canonical in confirmed_repairs.items():
            original = originals_by_placeholder.get(canonical, "")
            self.log_queue.put(("restore", f"[INFO] 已按用户确认修复占位符: {token} -> {canonical} -> {original}"))
        self.log_queue.put(("restore", f"[INFO] 还原完成: {output_path}"))
        self.root.after(0, lambda: self._after_restore_complete(output_path))

    def _after_restore_complete(self, output_path: Path) -> None:
        self.restore_output_var.set(str(output_path))
        self.restore_status_var.set("已完成")

    def _confirm_placeholder_repairs(self, input_path: Path, mapping_path: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]] | None:
        payload = read_mapping(mapping_path)
        items = mapping_entries(payload, only_enabled=False)
        repairs_by_pair: dict[tuple[str, str], PlaceholderRepair] = {}
        for text in collect_texts_for_path(input_path):
            for repair in suggest_placeholder_repairs(text, items, min_score=0.70):
                key = (repair.token, repair.canonical)
                current = repairs_by_pair.get(key)
                if current is None or repair.score > current.score:
                    repairs_by_pair[key] = repair
        repairs = sorted(repairs_by_pair.values(), key=lambda item: (item.canonical, item.token))
        if not repairs:
            return {}, {}, {}
        auto_repairs = {repair.token: repair.canonical for repair in repairs if repair.score >= 0.90}
        needs_confirmation = [repair for repair in repairs if repair.score < 0.90]
        if not needs_confirmation:
            return auto_repairs, auto_repairs, {}
        confirmed_repairs = self._show_placeholder_repair_dialog(needs_confirmation, payload)
        if confirmed_repairs is None:
            return None
        all_repairs = {**auto_repairs, **confirmed_repairs}
        return all_repairs, auto_repairs, confirmed_repairs

    def _show_placeholder_repair_dialog(self, repairs: list[PlaceholderRepair], payload: dict[str, object]) -> dict[str, str] | None:
        entries = payload.get("entries", [])
        by_placeholder = {
            str(entry.get("placeholder", "")): str(entry.get("original", ""))
            for entry in entries
            if isinstance(entry, dict)
        }
        dialog = tk.Toplevel(self.root)
        dialog.title("确认相似占位符")
        dialog.geometry("780x420")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text="发现一些可能被外部 AI 改坏的占位符，置信度不够高，不能自动判断。请用按钮确认是否按右侧占位符还原。",
            style="Field.TLabel",
            wraplength=730,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))

        tree = ttk.Treeview(
            dialog,
            columns=("enabled", "found", "canonical", "original", "score"),
            show="headings",
            height=12,
            style="Mapping.Treeview",
        )
        for key, label, width in [
            ("enabled", "使用", 60),
            ("found", "文件中出现", 180),
            ("canonical", "映射占位符", 180),
            ("original", "原始词", 240),
            ("score", "相似度", 90),
        ]:
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w", stretch=True)
        tree.grid(row=1, column=0, sticky="nsew", padx=14)

        selected: dict[str, bool] = {}
        for idx, repair in enumerate(repairs):
            iid = str(idx)
            selected[iid] = False
            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    "是" if selected[iid] else "否",
                    repair.token,
                    repair.canonical,
                    by_placeholder.get(repair.canonical, ""),
                    f"{repair.score:.2f}",
                ),
            )

        def set_enabled(iid: str, enabled: bool) -> None:
            selected[iid] = enabled
            values = list(tree.item(iid, "values"))
            values[0] = "是" if enabled else "否"
            tree.item(iid, values=values)

        def toggle_current() -> None:
            for iid in tree.selection():
                set_enabled(iid, not selected[iid])

        tree.bind("<Double-1>", lambda _event: toggle_current())

        result: dict[str, str] | None = None

        def confirm() -> None:
            nonlocal result
            result = {
                repairs[int(iid)].token: repairs[int(iid)].canonical
                for iid, is_selected in selected.items()
                if is_selected
            }
            dialog.destroy()

        def cancel() -> None:
            nonlocal result
            result = None
            dialog.destroy()

        action_row = ttk.Frame(dialog, padding=14)
        action_row.grid(row=2, column=0, sticky="ew")
        ttk.Button(action_row, text="确认选中项", style="Secondary.TButton", command=toggle_current).pack(side="left")
        ttk.Button(action_row, text="全选", style="Secondary.TButton", command=lambda: [set_enabled(iid, True) for iid in selected]).pack(side="left", padx=(8, 0))
        ttk.Button(action_row, text="全不选", style="Secondary.TButton", command=lambda: [set_enabled(iid, False) for iid in selected]).pack(side="left", padx=(8, 0))
        ttk.Button(action_row, text="确认并还原", style="Primary.TButton", command=confirm).pack(side="right")
        ttk.Button(action_row, text="取消", style="Secondary.TButton", command=cancel).pack(side="right", padx=(0, 8))

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        self.root.wait_window(dialog)
        return result
