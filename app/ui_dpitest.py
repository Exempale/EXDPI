"""Диалог DPI-теста — запускает TLS-handshake к набору хостов и показывает,
проходит ли соединение."""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Dict, List, Optional

from . import paths
from .dpi_test import DEFAULT_TARGETS, TestResult, run_async
from .theme import THEME

log = logging.getLogger("dpibypass.ui_dpitest")


class DpiTestDialog(tk.Toplevel):
    """Окно диагностики обхода — нажал «проверить», получил по каждому хосту
    зелёный/красный индикатор."""

    WIDTH = 420
    HEIGHT = 460

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("EXDPI · диагностика")
        self.configure(bg=THEME.bg)
        self.resizable(False, False)
        self.transient(master)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        try:
            ico = paths.icon_ico()
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

        self._rows: Dict[str, Dict[str, tk.Widget]] = {}
        self._results: List[TestResult] = []
        self._running = False

        self._build()

        # центрируем относительно master
        self.update_idletasks()
        try:
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
            mh = master.winfo_height()
            x = mx + (mw - self.WIDTH) // 2
            y = my + (mh - self.HEIGHT) // 2
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(10, min(x, sw - self.WIDTH - 10))
            y = max(10, min(y, sh - self.HEIGHT - 60))
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        except Exception:
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}")

        self.protocol("WM_DELETE_WINDOW", self._close)
        # запускаем тест сразу при открытии
        self.after(100, self._run_test)

    # ── layout ──────────────────────────────────────────────────────
    def _build(self) -> None:
        outer = tk.Frame(self, bg=THEME.bg, padx=22, pady=20)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer, text="ДИАГНОСТИКА",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer, text="DPI-обход",
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 13, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="TLS-handshake к каждому хосту с правильным SNI. "
                 "Если рукопожатие проходит — DPI-обход работает.",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9), anchor="w",
            wraplength=370, justify="left",
        ).pack(fill="x", pady=(6, 14))

        # список хостов с иконками статуса
        self._list = tk.Frame(outer, bg=THEME.bg)
        self._list.pack(fill="both", expand=True)

        for host in DEFAULT_TARGETS:
            self._add_row(host)

        # сводка
        self._summary = tk.Label(
            outer, text="—",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 10, "bold"), anchor="w",
        )
        self._summary.pack(fill="x", pady=(12, 6))

        # bottom row: re-run + close
        bottom = tk.Frame(outer, bg=THEME.bg)
        bottom.pack(fill="x", pady=(8, 0))

        self._rerun_btn = tk.Label(
            bottom, text="  проверить ещё раз  ",
            fg=THEME.bg, bg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"),
            cursor="hand2", padx=14, pady=8,
        )
        self._rerun_btn.pack(side="right")
        self._rerun_btn.bind("<Button-1>", lambda _e: self._run_test())
        self._rerun_btn.bind("<Enter>", lambda _e: self._rerun_btn.configure(bg=THEME.accent_dim))
        self._rerun_btn.bind("<Leave>", lambda _e: self._rerun_btn.configure(bg=THEME.accent))

        close = tk.Label(
            bottom, text="закрыть",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 10), cursor="hand2",
        )
        close.pack(side="left")
        close.bind("<Button-1>", lambda _e: self._close())

    def _add_row(self, host: str) -> None:
        row = tk.Frame(self._list, bg=THEME.bg)
        row.pack(fill="x", pady=3)

        # цветной индикатор слева
        dot = tk.Canvas(
            row, width=14, height=14, bg=THEME.bg,
            highlightthickness=0, bd=0,
        )
        dot.pack(side="left")
        dot.create_oval(2, 2, 12, 12, fill=THEME.text_muted, outline="")

        host_lbl = tk.Label(
            row, text=host,
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 10), anchor="w",
        )
        host_lbl.pack(side="left", padx=(8, 0))

        info = tk.Label(
            row, text="…",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9), anchor="e",
        )
        info.pack(side="right")

        self._rows[host] = {"dot": dot, "host": host_lbl, "info": info}

    # ── runtime ──────────────────────────────────────────────────────
    def _run_test(self) -> None:
        if self._running:
            return
        self._running = True
        self._results = []

        # сбросить состояние индикаторов
        for host, w in self._rows.items():
            dot = w["dot"]
            assert isinstance(dot, tk.Canvas)
            dot.delete("all")
            dot.create_oval(2, 2, 12, 12, fill=THEME.text_muted, outline="")
            info = w["info"]
            assert isinstance(info, tk.Label)
            info.configure(text="…", fg=THEME.text_muted)

        self._summary.configure(text="идёт проверка…", fg=THEME.text_secondary)
        self._rerun_btn.configure(bg=THEME.accent_dark, cursor="watch")

        def _on_progress(res: TestResult) -> None:
            # вызывается из потока — бунсим в UI
            self.after(0, lambda r=res: self._apply_result(r))

        def _on_done(_results: List[TestResult]) -> None:
            self.after(0, self._on_done_ui)

        run_async(
            targets=DEFAULT_TARGETS,
            timeout=5.0,
            on_progress=_on_progress,
            on_done=_on_done,
        )

    def _apply_result(self, res: TestResult) -> None:
        self._results.append(res)
        w = self._rows.get(res.host)
        if not w:
            return
        dot = w["dot"]
        info = w["info"]
        assert isinstance(dot, tk.Canvas)
        assert isinstance(info, tk.Label)

        dot.delete("all")
        if res.ok:
            color = THEME.track_on  # зелёный
            text = f"{res.elapsed_ms} мс"
            fg = THEME.accent_dim
        else:
            color = THEME.danger
            text = res.error or "ошибка"
            fg = THEME.danger
            # длинный текст ошибки укоротим
            if len(text) > 26:
                text = text[:24] + "…"

        dot.create_oval(2, 2, 12, 12, fill=color, outline="")
        info.configure(text=text, fg=fg)

    def _on_done_ui(self) -> None:
        self._running = False
        self._rerun_btn.configure(bg=THEME.accent, cursor="hand2")

        ok = sum(1 for r in self._results if r.ok)
        total = len(self._results)
        if ok == total and total > 0:
            self._summary.configure(
                text=f"всё проходит ({ok}/{total}) — DPI-обход работает",
                fg=THEME.accent_dim,
            )
        elif ok == 0 and total > 0:
            self._summary.configure(
                text=f"ничего не проходит ({ok}/{total}) — DPI режет всё",
                fg=THEME.danger,
            )
        else:
            self._summary.configure(
                text=f"проходит {ok} из {total} — частичный обход",
                fg=THEME.text_primary,
            )

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
