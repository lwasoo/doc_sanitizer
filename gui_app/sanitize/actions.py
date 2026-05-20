"""Background actions for scanning and applying sanitize mappings."""

from __future__ import annotations

import copy
from pathlib import Path
from tkinter import filedialog, messagebox

from doc_sanitizer import apply_mapping_to_file, read_mapping, scan_file
from doc_sanitizer.mapping import MappingPayload
from ..defaults import DEFAULT_MODEL, DEFAULT_OLLAMA_URL


class SanitizeActions:
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
        source_file = payload.source_file.strip()
        sanitized_file = payload.sanitized_file.strip()
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
            "prompt_language": self._scan_prompt_language(),
            "existing_payload": copy.deepcopy(self.current_mapping_data),
        }

    def _scan_prompt_language(self) -> str:
        value = self.sanitize_prompt_language_var.get().strip().lower()
        if value in {"中文", "zh", "chinese"}:
            return "zh"
        if value in {"english", "英文", "en"}:
            return "en"
        return "auto"

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
            prompt_language=str(params["prompt_language"]),
            existing_mapping_path=existing_map_path if existing_map_path.exists() else None,
            existing_payload=params["existing_payload"] if params["existing_payload"] is not None else None,
        )
        self.root.after(0, lambda: self._after_scan_complete(payload))

    def _after_scan_complete(self, payload: MappingPayload) -> None:
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
        if payload is None:
            raise ValueError("缺少映射数据，无法生成脱敏文档。")
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
        self._set_restore_mapping_path_if_empty(mapping_path)


