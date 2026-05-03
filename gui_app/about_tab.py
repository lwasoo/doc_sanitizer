from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from .defaults import APP_DISPLAY_NAME, APP_VERSION, GITHUB_RELEASES_URL
from .self_update import can_self_update_with_asset, launch_self_updater
from .update_checker import UpdateInfo, download_release_asset, fetch_latest_release


class AboutTabMixin:
    def _build_about_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        card = ttk.Frame(parent, style="Card.TFrame", padding=24)
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text=APP_DISPLAY_NAME, style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=f"当前版本: v{APP_VERSION}", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(card, text="感谢支持合规工作～(∠・ω< )⌒★", style="AboutThanks.TLabel").grid(row=2, column=0, sticky="w", pady=(24, 0))
        ttk.Label(
            card,
            text=(
                "本工具面向文档整理、脱敏与还原等合规场景。"
                "由于文档格式、图片 OCR、规则识别、本地模型识别、外部 AI 改写和人工编辑都可能带来遗漏或误判，"
                "工具无法保证 100% 消除数据保密、隐私保护、商业秘密或其他合规风险。"
                "对外发送或归档前，请务必进行人工复核。"
            ),
            style="RiskNotice.TLabel",
            wraplength=720,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(14, 0))

        self.latest_update_info: UpdateInfo | None = None
        self.update_status_var = self._make_string_var("等待检测更新")
        ttk.Label(card, textvariable=self.update_status_var, style="Status.TLabel").grid(row=4, column=0, sticky="w", pady=(24, 0))

        action_row = ttk.Frame(card, style="Card.TFrame")
        action_row.grid(row=5, column=0, sticky="w", pady=(14, 0))
        self.check_update_button = ttk.Button(
            action_row,
            text="检测更新",
            style="Primary.TButton",
            command=lambda: self.check_updates_async(silent=False),
        )
        self.check_update_button.pack(side="left")
        self.download_update_button = ttk.Button(
            action_row,
            text="下载更新包",
            style="Secondary.TButton",
            command=self.download_latest_update_async,
            state="disabled",
        )
        self.download_update_button.pack(side="left", padx=(10, 0))
        ttk.Button(action_row, text="打开 Release 页面", style="Secondary.TButton", command=lambda: webbrowser.open(GITHUB_RELEASES_URL)).pack(side="left", padx=(10, 0))

        ttk.Label(
            card,
            text="检测到新版本后会下载对应平台的 Release 安装包。打包后的 Windows exe / macOS app 可在下载后关闭当前程序并自动替换重启，源码运行不启用自动替换。",
            style="Hint.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=6, column=0, sticky="w", pady=(18, 0))

    def _make_string_var(self, value: str):
        import tkinter as tk

        return tk.StringVar(value=value)

    def check_updates_async(self, silent: bool = True) -> None:
        if hasattr(self, "check_update_button"):
            self.check_update_button.configure(state="disabled")
        self.update_status_var.set("正在检测更新...")
        threading.Thread(target=self._check_updates_worker, args=(silent,), daemon=True).start()

    def _check_updates_worker(self, silent: bool) -> None:
        try:
            info = fetch_latest_release()
        except Exception as exc:
            self.root.after(0, lambda: self._handle_update_error(exc, silent))
            return
        self.root.after(0, lambda: self._handle_update_result(info, silent))

    def _handle_update_result(self, info: UpdateInfo, silent: bool) -> None:
        if hasattr(self, "check_update_button"):
            self.check_update_button.configure(state="normal")
        if info.is_update_available:
            self.latest_update_info = info
            if hasattr(self, "download_update_button"):
                self.download_update_button.configure(state="normal")
            self.update_status_var.set(f"发现新版本 v{info.latest_version}")
            if silent:
                self.download_latest_update_async()
                return
            should_download = messagebox.askyesno(
                "发现新版本",
                f"当前版本: v{info.current_version}\n最新版本: v{info.latest_version}\n\n是否现在下载更新包？",
            )
            if should_download:
                self.download_latest_update_async()
            return

        self.latest_update_info = None
        if hasattr(self, "download_update_button"):
            self.download_update_button.configure(state="disabled")
        self.update_status_var.set(f"已是最新版本 v{info.current_version}")
        if not silent:
            messagebox.showinfo("检测更新", f"当前已是最新版本：v{info.current_version}")

    def _handle_update_error(self, exc: Exception, silent: bool) -> None:
        if hasattr(self, "check_update_button"):
            self.check_update_button.configure(state="normal")
        self.update_status_var.set("检测更新失败")
        if not silent:
            messagebox.showerror("检测更新失败", str(exc))

    def download_latest_update_async(self) -> None:
        info = self.latest_update_info
        if info is None:
            messagebox.showinfo("没有可下载版本", "请先检测更新。")
            return
        if hasattr(self, "download_update_button"):
            self.download_update_button.configure(state="disabled")
        self.update_status_var.set(f"正在下载 v{info.latest_version} 更新包...")
        threading.Thread(target=self._download_latest_update_worker, args=(info,), daemon=True).start()

    def _download_latest_update_worker(self, info: UpdateInfo) -> None:
        try:
            path = download_release_asset(info)
        except Exception as exc:
            self.root.after(0, lambda: self._handle_update_download_error(exc))
            return
        self.root.after(0, lambda: self._handle_update_download_complete(path))

    def _handle_update_download_complete(self, path: Path) -> None:
        if hasattr(self, "download_update_button"):
            self.download_update_button.configure(state="normal")
        self.update_status_var.set(f"更新包已下载：{path}")
        if can_self_update_with_asset(path):
            install_now = messagebox.askyesno(
                "下载完成",
                f"更新包已下载到：\n{path}\n\n是否关闭当前程序并自动替换为新版本？",
            )
            if install_now:
                try:
                    launch_self_updater(path)
                except Exception as exc:
                    messagebox.showerror("自动安装失败", str(exc))
                    return
                self.root.destroy()
            return

        open_folder = messagebox.askyesno(
            "下载完成",
            f"更新包已下载到：\n{path}\n\n当前运行方式不支持自动替换，是否打开所在文件夹？",
        )
        if open_folder:
            if hasattr(self, "_open_path_in_file_manager"):
                self._open_path_in_file_manager(path)
            else:
                webbrowser.open(str(path.parent))

    def _handle_update_download_error(self, exc: Exception) -> None:
        if hasattr(self, "download_update_button"):
            self.download_update_button.configure(state="normal")
        self.update_status_var.set("下载更新包失败")
        messagebox.showerror("下载更新包失败", str(exc))
