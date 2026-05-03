#!/usr/bin/env python3
"""Tkinter GUI entrypoint."""

from __future__ import annotations

import ctypes
import json
import locale
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .about_tab import AboutTabMixin
from .convert_tab import ConvertTabMixin
from .defaults import APP_DISPLAY_NAME, APP_VERSION, DEFAULT_MODEL, DEFAULT_OLLAMA_URL
from .prompt_tab import PromptTabMixin
from .restore_tab import RestoreTabMixin
from .sanitize_tab import SanitizeTabMixin
from office_conversion import LIBREOFFICE_DOWNLOAD_URL, OfficeConversionError


def configure_windows_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class ConverterGUI(ConvertTabMixin, SanitizeTabMixin, RestoreTabMixin, PromptTabMixin, AboutTabMixin):
    def __init__(self, root: tk.Tk, geometry: str | None = None) -> None:
        self.root = root
        self.root.title(f"{APP_DISPLAY_NAME} v{APP_VERSION}")
        self.root.geometry(geometry or "1280x820")
        self.root.minsize(1040, 700)

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.process: subprocess.Popen[bytes] | None = None
        self.worker_running = False

        self.docx_var = tk.StringVar()
        self.template_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.ollama_url_var = tk.StringVar(value=DEFAULT_OLLAMA_URL)
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.timeout_var = tk.StringVar(value="180")
        self.retries_var = tk.StringVar(value="2")
        self.no_llm_var = tk.BooleanVar(value=False)
        self.layout_mode_var = tk.StringVar(value="formal")
        self.theme_var = tk.StringVar(value="formal_blue")
        self.diversity_var = tk.StringVar(value="none")
        self.seed_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="就绪")

        self.sanitize_input_var = tk.StringVar()
        self.sanitize_output_var = tk.StringVar()
        self.sanitize_mapping_var = tk.StringVar()
        self.sanitize_status_var = tk.StringVar(value="等待识别")
        self.sanitize_use_llm_var = tk.BooleanVar(value=True)

        self.restore_input_var = tk.StringVar()
        self.restore_output_var = tk.StringVar()
        self.restore_mapping_var = tk.StringVar()
        self.restore_status_var = tk.StringVar(value="就绪")

        self.manual_sensitive_var = tk.StringVar()
        self.manual_placeholder_var = tk.StringVar()
        self.mapping_search_var = tk.StringVar()
        self.current_mapping_data: dict[str, object] | None = None
        self.scan_ready = False
        self.mapping_editor: tk.Entry | None = None
        self.mapping_editor_item: str | None = None
        self.mapping_editor_column: str | None = None
        self.batch_placeholder_text = "示例：\nCOMPANY|Google LLC\nPERSON|张三\n示例项目=>__PROJECT_008__\n某某科技有限公司"
        self.manual_sensitive_placeholder = "输入敏感词，例如：Google LLC"
        self.manual_placeholder_hint = "可留空；也可写 COMPANY 或 __COMPANY_010__"
        self.app_icon_image: tk.PhotoImage | None = None

        self._configure_style()
        self._apply_window_icon()
        self._build_ui()
        self._setup_placeholder_hints()
        self._update_sanitize_action_states()
        self._pump_logs()
        self.root.after(300, self.detect_models_async)
        self.root.after(1800, lambda: self.check_updates_async(silent=True))

    def _resource_path(self, relative_path: str) -> Path:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / relative_path
        return Path(__file__).resolve().parent.parent / relative_path

    def _apply_window_icon(self) -> None:
        icon_png = self._resource_path("assets/icon.png")
        icon_ico = self._resource_path("assets/icon.ico")
        try:
            if icon_png.exists():
                self.app_icon_image = tk.PhotoImage(file=str(icon_png))
                self.root.iconphoto(True, self.app_icon_image)
        except Exception:
            self.app_icon_image = None
        if sys.platform == "win32":
            try:
                if icon_ico.exists():
                    self.root.iconbitmap(str(icon_ico))
            except Exception:
                pass

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass

        self.root.configure(bg="#f6f8fb")
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("App.TFrame", background="#f6f8fb")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Header.TFrame", background="#f6f8fb")
        style.configure("HeaderAccent.TFrame", background="#2f6fed")
        style.configure("HeaderTitle.TLabel", background="#f6f8fb", foreground="#17324d", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("HeaderSub.TLabel", background="#f6f8fb", foreground="#70849a", font=("Microsoft YaHei UI", 9))
        style.configure("AboutThanks.TLabel", background="#ffffff", foreground="#17324d", font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("RiskNotice.TLabel", background="#ffffff", foreground="#9a3b2f", font=("Microsoft YaHei UI", 10))
        style.configure("Section.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("Section.TLabelframe.Label", background="#ffffff", foreground="#17324d", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Field.TLabel", background="#ffffff", foreground="#2f485f")
        style.configure("Hint.TLabel", background="#ffffff", foreground="#7b8da1", font=("Microsoft YaHei UI", 9))
        style.configure("Status.TLabel", background="#ffffff", foreground="#5f7389", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", padding=(10, 6))
        style.configure("TEntry", padding=(6, 4))
        style.configure("TCombobox", padding=(6, 4))
        style.configure("TNotebook", background="#f6f8fb", borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", padding=(14, 8), font=("Microsoft YaHei UI", 10), background="#edf2f8", foreground="#5d7188", borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#ffffff"), ("active", "#f2f6fb")], foreground=[("selected", "#2f6fed"), ("active", "#2f6fed")])
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(11, 6))
        style.configure("Secondary.TButton", padding=(10, 6))
        style.configure("Mapping.Treeview", rowheight=32, font=("Microsoft YaHei UI", 11), borderwidth=0)
        style.configure("Mapping.Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), background="#f5f8fc", foreground="#2f485f")

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=14)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Header.TFrame", padding=(0, 0, 0, 10))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        accent = ttk.Frame(header, style="HeaderAccent.TFrame", height=3)
        accent.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        title_wrap = ttk.Frame(header, style="Header.TFrame", padding=(4, 0, 0, 0))
        title_wrap.grid(row=1, column=0, sticky="ew")
        title_wrap.columnconfigure(0, weight=1)
        ttk.Label(title_wrap, text=APP_DISPLAY_NAME, style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(title_wrap, text=f"月报转 PPT / 文档脱敏 / 文档还原 / v{APP_VERSION}", style="HeaderSub.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        notebook = ttk.Notebook(shell)
        notebook.grid(row=1, column=0, sticky="nsew")

        convert_tab = ttk.Frame(notebook, style="App.TFrame", padding=6)
        sanitize_tab = ttk.Frame(notebook, style="App.TFrame", padding=6)
        restore_tab = ttk.Frame(notebook, style="App.TFrame", padding=6)
        prompt_tab = ttk.Frame(notebook, style="App.TFrame", padding=6)
        about_tab = ttk.Frame(notebook, style="App.TFrame", padding=6)
        notebook.add(convert_tab, text="月报转 PPT")
        notebook.add(sanitize_tab, text="脱敏")
        notebook.add(restore_tab, text="还原")
        notebook.add(prompt_tab, text="AI Prompt")
        notebook.add(about_tab, text="关于")

        self._build_convert_tab(convert_tab)
        self._build_sanitize_tab(sanitize_tab)
        self._build_restore_tab(restore_tab)
        self._build_prompt_tab(prompt_tab)
        self._build_about_tab(about_tab)

    def _create_log_widget(self, parent: ttk.Frame) -> ScrolledText:
        widget = ScrolledText(
            parent,
            height=12,
            wrap=tk.WORD,
            font=("Cascadia Mono", 11),
            background="#0f1720",
            foreground="#d9e7f5",
            insertbackground="#d9e7f5",
            relief=tk.FLAT,
            padx=12,
            pady=12,
        )
        widget.tag_configure("INFO", foreground="#d9e7f5")
        widget.tag_configure("WARN", foreground="#ffd866")
        widget.tag_configure("ERROR", foreground="#ff6b6b")
        widget.tag_configure("NOTICE", foreground="#72d4ff")
        widget.configure(state=tk.DISABLED)
        return widget

    def _setup_placeholder_hints(self) -> None:
        self._install_entry_placeholder(self.manual_sensitive_entry, self.manual_sensitive_var, self.manual_sensitive_placeholder)
        self._install_entry_placeholder(self.manual_placeholder_entry, self.manual_placeholder_var, self.manual_placeholder_hint)
        self._install_text_placeholder(self.batch_add_text, self.batch_placeholder_text)

    @staticmethod
    def _install_entry_placeholder(entry: tk.Entry, var: tk.StringVar, placeholder: str) -> None:
        normal_fg = "#111111"
        placeholder_fg = "#9aa8b6"

        def show_placeholder() -> None:
            if not var.get():
                entry.configure(fg=placeholder_fg)
                var.set(placeholder)
                entry.selection_clear()

        def clear_placeholder() -> None:
            if entry.cget("fg") == placeholder_fg and var.get() == placeholder:
                var.set("")
                entry.configure(fg=normal_fg)

        show_placeholder()
        entry.bind("<FocusIn>", lambda _e: clear_placeholder(), add="+")
        entry.bind("<FocusOut>", lambda _e: show_placeholder() if not var.get().strip() else entry.configure(fg=normal_fg), add="+")

    @staticmethod
    def _install_text_placeholder(widget: tk.Text, placeholder: str) -> None:
        normal_fg = "#111111"
        placeholder_fg = "#9aa8b6"

        def show_placeholder() -> None:
            if widget.get("1.0", tk.END).strip():
                return
            widget.configure(fg=placeholder_fg)
            widget.delete("1.0", tk.END)
            widget.insert("1.0", placeholder)

        def clear_placeholder() -> None:
            if widget.cget("fg") == placeholder_fg:
                widget.delete("1.0", tk.END)
                widget.configure(fg=normal_fg)

        show_placeholder()
        widget.bind("<FocusIn>", lambda _e: clear_placeholder(), add="+")
        widget.bind("<FocusOut>", lambda _e: show_placeholder() if not widget.get("1.0", tk.END).strip() else widget.configure(fg=normal_fg), add="+")

    def _add_path_row(self, frame: ttk.Frame, row: int, label: str, var: tk.StringVar, browse_cmd) -> None:
        ttk.Label(frame, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=6)
        row_frame = ttk.Frame(frame, style="Card.TFrame")
        row_frame.grid(row=row, column=1, sticky="ew", pady=6)
        row_frame.columnconfigure(0, weight=1)
        ttk.Entry(row_frame, textvariable=var).grid(row=0, column=0, sticky="ew")
        ttk.Button(row_frame, text="浏览", command=browse_cmd).grid(row=0, column=1, padx=(8, 0))

    def _get_log_widget(self, target: str) -> ScrolledText:
        if target == "sanitize":
            return self.mask_log_text
        if target == "restore":
            return self.restore_log_text
        return self.log_text

    def append_log(self, msg: str, target: str) -> None:
        widget = self._get_log_widget(target)
        tag = self._log_tag_for_message(msg)
        widget.configure(state=tk.NORMAL)
        widget.insert(tk.END, msg + "\n", tag)
        widget.see(tk.END)
        widget.configure(state=tk.DISABLED)

    @staticmethod
    def _log_tag_for_message(msg: str) -> str:
        upper = msg.upper()
        if "外部 AI 使用提醒" in msg:
            return "NOTICE"
        if "[ERROR]" in upper:
            return "ERROR"
        if "[WARN]" in upper:
            return "WARN"
        return "INFO"

    def _pump_logs(self) -> None:
        try:
            while True:
                target, msg = self.log_queue.get_nowait()
                self.append_log(msg, target)
        except queue.Empty:
            pass
        self.root.after(100, self._pump_logs)

    def detect_models(self) -> None:
        self.detect_models_async(silent=False)

    def detect_models_async(self, silent: bool = True) -> None:
        url = self.ollama_url_var.get().strip().rstrip("/") + "/api/tags"
        threading.Thread(target=self._detect_models_worker, args=(silent, url), daemon=True).start()

    def _detect_models_worker(self, silent: bool, url: str) -> None:
        try:
            req = urllib.request.Request(url=url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
            self.root.after(0, lambda: self._apply_models(models, silent))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            models = self._detect_models_from_cli()
            if models:
                self.root.after(0, lambda: self._apply_models(models, silent))
                self.log_queue.put(("convert", f"[WARN] HTTP 检测失败，已回退到 ollama list: {exc}"))
            else:
                self.root.after(0, lambda: self._handle_model_detect_error(exc, silent))

    def _detect_models_from_cli(self) -> list[str]:
        try:
            completed = subprocess.run(["ollama", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, check=False)
            if completed.returncode != 0:
                return []
            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            return [line.split()[0] for line in lines[1:] if line.split()]
        except Exception:
            return []

    def _apply_models(self, models: list[str], silent: bool) -> None:
        if not models:
            if not silent:
                messagebox.showinfo("检测结果", "未检测到模型。")
            self.log_queue.put(("convert", "[WARN] 未检测到可用模型"))
            return
        self.model_combo["values"] = models
        self.sanitize_model_combo["values"] = models
        if self.model_var.get() not in models:
            self.model_var.set(models[0])
        self.log_queue.put(("convert", f"[INFO] 检测到模型: {', '.join(models)}"))
        self.log_queue.put(("sanitize", f"[INFO] 检测到模型: {', '.join(models)}"))

    def _handle_model_detect_error(self, exc: Exception, silent: bool) -> None:
        self.log_queue.put(("convert", f"[WARN] 模型检测失败: {exc}"))
        self.log_queue.put(("sanitize", f"[WARN] 模型检测失败: {exc}"))
        if not silent:
            messagebox.showerror("检测失败", f"无法检测模型：{exc}")

    def _start_worker(self, target: str, status_var: tk.StringVar, start_msg: str, func: Callable[[], None]) -> None:
        if self.worker_running or (self.process and self.process.poll() is None):
            messagebox.showinfo("正在运行", "当前已有任务在运行。")
            return
        self.worker_running = True
        status_var.set("运行中")
        self.log_queue.put((target, start_msg))

        def runner() -> None:
            try:
                func()
            except OfficeConversionError as exc:
                self.root.after(0, status_var.set, "运行失败")
                self.root.after(0, self._show_office_conversion_error, exc)
                self.log_queue.put((target, f"[ERROR] {exc}"))
            except Exception as exc:
                self.root.after(0, status_var.set, "运行失败")
                self.log_queue.put((target, f"[ERROR] {exc}"))
            finally:
                self.root.after(0, self._mark_worker_idle)

        threading.Thread(target=runner, daemon=True).start()

    def _mark_worker_idle(self) -> None:
        self.worker_running = False

    def _show_office_conversion_error(self, exc: OfficeConversionError) -> None:
        open_page = messagebox.askyesno(
            "需要安装 LibreOffice",
            f"{exc}\n\n是否打开 LibreOffice 下载页面？",
        )
        if open_page:
            webbrowser.open(LIBREOFFICE_DOWNLOAD_URL)

    def _open_path_in_file_manager(self, path: Path) -> None:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            webbrowser.open(str(path.parent))

    def _resolve_script(self, script_name: str) -> Path | None:
        local = Path(__file__).resolve().parent.parent / script_name
        if local.exists():
            return local
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / script_name
            if bundled.exists():
                return bundled
        return None

    @staticmethod
    def _unique_output_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 2
        while True:
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def _start_subprocess(self, cmd: list[str], target: str, status_var: tk.StringVar, start_msg: str, on_success: Callable[[], None] | None = None) -> None:
        status_var.set("运行中")
        self.log_queue.put((target, start_msg))
        self.log_queue.put((target, "[CMD] " + " ".join(f'"{x}"' if " " in x else x for x in cmd)))
        threading.Thread(target=self._run_process, args=(cmd, target, status_var, on_success), daemon=True).start()

    def _run_process(self, cmd: list[str], target: str, status_var: tk.StringVar, on_success: Callable[[], None] | None) -> None:
        try:
            child_env = os.environ.copy()
            child_env["PYTHONIOENCODING"] = "utf-8"
            child_env["PYTHONUTF8"] = "1"
            child_env["PYTHONUNBUFFERED"] = "1"
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=False, env=child_env, bufsize=0)
            assert self.process.stdout is not None
            while True:
                raw = self.process.stdout.readline()
                if not raw:
                    if self.process.poll() is not None:
                        break
                    continue
                self.log_queue.put((target, self._decode_output_line(raw).rstrip("\r\n")))
            code = self.process.wait()
            if code == 0:
                self.root.after(0, status_var.set, "已完成")
                self.log_queue.put((target, "[INFO] 任务完成。"))
                if on_success:
                    self.root.after(0, on_success)
            else:
                self.root.after(0, status_var.set, "运行失败")
                self.log_queue.put((target, f"[ERROR] 任务失败，退出码={code}"))
        except Exception as exc:
            self.root.after(0, status_var.set, "启动失败")
            self.log_queue.put((target, f"[ERROR] 启动失败: {exc}"))
        finally:
            self.process = None

    @staticmethod
    def _decode_output_line(raw: bytes) -> str:
        for enc in ("utf-8", locale.getpreferredencoding(False), "gbk", "cp936"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("utf-8", errors="replace")

    def stop_task(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.status_var.set("已停止")
            self.log_queue.put(("convert", "[INFO] 已请求停止任务。"))
            return
        self.log_queue.put(("convert", "[INFO] 当前无可终止的子进程任务。"))


def main() -> int:
    geometry = None
    if "--geometry" in sys.argv:
        idx = sys.argv.index("--geometry")
        if idx + 1 >= len(sys.argv):
            print("missing value for --geometry, expected WxH", file=sys.stderr)
            return 2
        geometry = sys.argv[idx + 1]
        if not re.fullmatch(r"\d+x\d+", geometry):
            print("invalid --geometry format, expected WxH like 1366x768", file=sys.stderr)
            return 2
        del sys.argv[idx : idx + 2]

    if "--run-cli" in sys.argv:
        idx = sys.argv.index("--run-cli")
        forward = [sys.argv[0], *sys.argv[idx + 1 :]]
        import docx_to_ppt_converter

        old_argv = sys.argv
        try:
            sys.argv = forward
            return int(docx_to_ppt_converter.main())
        finally:
            sys.argv = old_argv

    if "--run-sanitize-cli" in sys.argv:
        idx = sys.argv.index("--run-sanitize-cli")
        forward = [sys.argv[0], *sys.argv[idx + 1 :]]
        import sanitize_docx

        old_argv = sys.argv
        try:
            sys.argv = forward
            return int(sanitize_docx.main())
        finally:
            sys.argv = old_argv

    configure_windows_dpi()
    root = tk.Tk()
    ConverterGUI(root, geometry=geometry)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
