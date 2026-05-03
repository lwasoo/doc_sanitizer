from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from doc_sanitizer.fuzzy_mapping import build_external_ai_prompt_sections, payload_from_json_text


class PromptTabMixin:
    def _build_prompt_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        main = ttk.PanedWindow(parent, orient="horizontal")
        main.grid(row=0, column=0, sticky="nsew")

        left_card = ttk.Frame(main, style="Card.TFrame", padding=18)
        right_card = ttk.Frame(main, style="Card.TFrame", padding=18)
        main.add(left_card, weight=5)
        main.add(right_card, weight=5)

        left_card.columnconfigure(0, weight=1)
        left_card.rowconfigure(1, weight=1)
        right_card.columnconfigure(0, weight=1)
        right_card.rowconfigure(1, weight=1, minsize=420)

        input_group = ttk.LabelFrame(left_card, text="1. 输入映射 JSON", style="Section.TLabelframe", padding=14)
        input_group.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            input_group,
            text="粘贴脱敏生成的映射 JSON，或从文件载入。工具会整理占位符规则，并提示可能指向同一对象的占位符。",
            style="Hint.TLabel",
            wraplength=480,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        input_actions = ttk.Frame(input_group, style="Card.TFrame")
        input_actions.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Button(input_actions, text="载入 JSON 文件", style="Secondary.TButton", command=self.load_prompt_mapping_json).pack(side="left")
        ttk.Button(input_actions, text="使用当前脱敏映射", style="Secondary.TButton", command=self.use_current_mapping_for_prompt).pack(side="left", padx=(8, 0))
        ttk.Button(input_actions, text="生成 Prompt", style="Primary.TButton", command=self.generate_external_ai_prompt).pack(side="left", padx=(8, 0))

        self.prompt_json_text = ScrolledText(
            left_card,
            height=20,
            wrap=tk.WORD,
            font=("Cascadia Mono", 10),
            background="#ffffff",
            foreground="#111111",
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.prompt_json_text.grid(row=1, column=0, sticky="nsew", pady=(14, 0))

        output_group = ttk.LabelFrame(right_card, text="2. 可复制给外部 AI 的 Prompt", style="Section.TLabelframe", padding=14)
        output_group.grid(row=0, column=0, sticky="ew")
        self.prompt_status_var = tk.StringVar(value="等待生成")
        ttk.Label(output_group, textvariable=self.prompt_status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        output_actions = ttk.Frame(output_group, style="Card.TFrame")
        output_actions.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Button(output_actions, text="复制 Prompt", style="Secondary.TButton", command=self.copy_external_ai_prompt).pack(side="left")
        ttk.Button(output_actions, text="保存 Prompt", style="Secondary.TButton", command=self.save_external_ai_prompt).pack(side="left", padx=(8, 0))
        ttk.Button(output_actions, text="清空", style="Secondary.TButton", command=self.clear_prompt_tab).pack(side="left", padx=(8, 0))

        right_panes = ttk.PanedWindow(right_card, orient="vertical")
        right_panes.grid(row=1, column=0, sticky="nsew", pady=(14, 0))

        prompt_text_frame = ttk.Frame(right_panes, style="Card.TFrame")
        prompt_text_frame.columnconfigure(0, weight=1)
        prompt_text_frame.rowconfigure(0, weight=1)
        right_panes.add(prompt_text_frame, weight=3)

        self.prompt_output_text = ScrolledText(
            prompt_text_frame,
            height=13,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 10),
            background="#ffffff",
            foreground="#111111",
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.prompt_output_text.grid(row=0, column=0, sticky="nsew")

        audit_group = ttk.LabelFrame(right_panes, text="3. 内部审核说明", style="Section.TLabelframe", padding=14)
        audit_group.columnconfigure(0, weight=1)
        audit_group.rowconfigure(0, weight=1)
        right_panes.add(audit_group, weight=2)

        self.prompt_audit_text = ScrolledText(
            audit_group,
            height=14,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 10),
            background="#fffaf0",
            foreground="#111111",
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.prompt_audit_text.grid(row=0, column=0, sticky="nsew")

    def load_prompt_mapping_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8")
            payload_from_json_text(raw)
        except Exception as exc:
            messagebox.showerror("载入失败", f"无法读取映射 JSON：{exc}")
            return
        self.prompt_json_text.delete("1.0", tk.END)
        self.prompt_json_text.insert("1.0", raw)
        self.prompt_status_var.set(f"已载入：{Path(path).name}")

    def use_current_mapping_for_prompt(self) -> None:
        if not getattr(self, "current_mapping_data", None):
            messagebox.showwarning("没有当前映射", "请先在脱敏页识别或载入映射 JSON。")
            return
        raw = json.dumps(self.current_mapping_data, ensure_ascii=False, indent=2)
        self.prompt_json_text.delete("1.0", tk.END)
        self.prompt_json_text.insert("1.0", raw)
        self.prompt_status_var.set("已使用当前脱敏映射")

    def generate_external_ai_prompt(self) -> None:
        raw = self.prompt_json_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("缺少 JSON", "请先粘贴或载入映射 JSON。")
            return
        try:
            payload = payload_from_json_text(raw)
            prompt, audit = build_external_ai_prompt_sections(payload)
        except Exception as exc:
            messagebox.showerror("生成失败", f"无法生成 Prompt：{exc}")
            return
        self.prompt_output_text.delete("1.0", tk.END)
        self.prompt_output_text.insert("1.0", prompt)
        self.prompt_audit_text.delete("1.0", tk.END)
        self.prompt_audit_text.insert("1.0", audit)
        count = len(payload.get("entries", []))
        self.prompt_status_var.set(f"已生成 Prompt，映射 {count} 条")

    def copy_external_ai_prompt(self) -> None:
        prompt = self.prompt_output_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("没有内容", "请先生成 Prompt。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(prompt)
        self.prompt_status_var.set("Prompt 已复制到剪贴板")

    def save_external_ai_prompt(self) -> None:
        prompt = self.prompt_output_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("没有内容", "请先生成 Prompt。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not path:
            return
        Path(path).write_text(prompt, encoding="utf-8")
        self.prompt_status_var.set(f"Prompt 已保存：{Path(path).name}")

    def clear_prompt_tab(self) -> None:
        self.prompt_json_text.delete("1.0", tk.END)
        self.prompt_output_text.delete("1.0", tk.END)
        self.prompt_audit_text.delete("1.0", tk.END)
        self.prompt_status_var.set("等待生成")
