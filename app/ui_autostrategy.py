"""Диалог авто-подбора стратегии zapret.

Запускает по очереди каждую general*.bat, тестирует TLS-handshake по набору
заблокированных хостов и показывает живой счёт. По завершении предлагает
применить лучшую стратегию (сохраняется в zapret_strategy_auto_result,
zapret_strategy = "auto").

На время прогона основной обход останавливается (WinDivert-фильтр в системе
один) и восстанавливается после.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

from . import paths
from .strategy_auto import StrategyScore, pick_best, run_auto_select_async
from .theme import THEME
from .zapret_runner import list_strategies

log = logging.getLogger("dpibypass.ui_autostrategy")


class AutoStrategyDialog(tk.Toplevel):
    WIDTH = 520
    HEIGHT = 600

    def __init__(
        self,
        master: tk.Misc,
        controller,
        on_applied: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(master)
        self.ctl = controller
        self._on_applied = on_applied
        self._cancelled = False
        self._running = False
        self._was_on = False
        self._best: Optional[StrategyScore] = None
        self._rows: Dict[str, Dict[str, tk.Label]] = {}
        self._anim_phase = 0.0
        self._anim_job: Optional[str] = None

        self.title("EXDPI · авто-подбор стратегии")
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

        self._build()
        self._center(master)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(150, self._start_run)

    # ── layout ───────────────────────────────────────────────────────

    def _center(self, master: tk.Misc) -> None:
        self.update_idletasks()
        try:
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            x = mx + (mw - self.WIDTH) // 2
            y = my + (mh - self.HEIGHT) // 2
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(10, min(x, sw - self.WIDTH - 10))
            y = max(10, min(y, sh - self.HEIGHT - 60))
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        except Exception:
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}")

    def _build(self) -> None:
        outer = tk.Frame(self, bg=THEME.bg, padx=22, pady=20)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer, text="АВТО-ПОДБОР",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer, text="Лучшая стратегия zapret",
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 13, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="Каждая стратегия запускается на пару секунд и проверяется "
                 "TLS-тестом по заблокированным хостам. Побеждает та, что "
                 "открыла больше всего хостов быстрее всех.",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9), anchor="w",
            wraplength=470, justify="left",
        ).pack(fill="x", pady=(6, 12))

        # ── индикатор прогресса (бегущая полоска) ───────────────────
        self._bar = tk.Canvas(outer, height=4, bg=THEME.card, highlightthickness=0, bd=0)
        self._bar.pack(fill="x")
        self._status = tk.Label(
            outer, text="Подготовка…",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9), anchor="w",
        )
        self._status.pack(fill="x", pady=(6, 10))

        # ── скроллируемый список стратегий ──────────────────────────
        mid = tk.Frame(outer, bg=THEME.bg)
        mid.pack(fill="both", expand=True)
        canvas = tk.Canvas(mid, bg=THEME.bg, highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        body = tk.Frame(canvas, bg=THEME.bg)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(body_id, width=e.width))

        def _on_wheel(e: tk.Event):
            try:
                delta = int(-1 * (e.delta / 120))
            except Exception:
                delta = -1 if getattr(e, "num", 0) == 4 else 1
            canvas.yview_scroll(delta, "units")
            return "break"

        for w in (canvas, body, self):
            w.bind("<MouseWheel>", _on_wheel, add="+")
            w.bind("<Button-4>", _on_wheel, add="+")
            w.bind("<Button-5>", _on_wheel, add="+")

        self._body = body
        self._wheel_handler = _on_wheel
        for strategy in list_strategies():
            self._add_row(strategy)

        # ── низ: кнопки ─────────────────────────────────────────────
        bottom = tk.Frame(outer, bg=THEME.bg)
        bottom.pack(fill="x", pady=(12, 0))

        self._apply_btn = tk.Label(
            bottom, text="  применить лучшую  ",
            fg=THEME.text_muted, bg=THEME.card,
            font=(THEME.font_ui, 10, "bold"),
            padx=14, pady=8,
        )
        self._apply_btn.pack(side="right")

        self._cancel_btn = tk.Label(
            bottom, text="  отменить  ",
            fg=THEME.text_secondary, bg=THEME.card,
            font=(THEME.font_ui, 10), cursor="hand2",
            padx=14, pady=8,
        )
        self._cancel_btn.pack(side="left")
        self._cancel_btn.bind("<Button-1>", lambda _e: self._close())

    def _add_row(self, strategy: str) -> None:
        row = tk.Frame(self._body, bg=THEME.bg, pady=2)
        row.pack(fill="x")
        name = tk.Label(
            row, text=self._short(strategy),
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_mono, 9), anchor="w",
        )
        name.pack(side="left")
        score = tk.Label(
            row, text="·",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_mono, 9), anchor="e",
        )
        score.pack(side="right")
        for w in (row, name, score):
            w.bind("<MouseWheel>", self._wheel_handler, add="+")
            w.bind("<Button-4>", self._wheel_handler, add="+")
            w.bind("<Button-5>", self._wheel_handler, add="+")
        self._rows[strategy] = {"name": name, "score": score}

    @staticmethod
    def _short(strategy: str) -> str:
        n = strategy[:-4] if strategy.endswith(".bat") else strategy
        return n

    # ── анимация прогресс-бара ───────────────────────────────────────

    def _animate_bar(self) -> None:
        if not self._running:
            try:
                self._bar.delete("sweep")
            except Exception:
                pass
            self._anim_job = None
            return
        try:
            w = max(self._bar.winfo_width(), 1)
            self._bar.delete("sweep")
            seg = max(60, w // 4)
            self._anim_phase = (self._anim_phase + 0.022) % 1.0
            x = int(self._anim_phase * (w + seg)) - seg
            self._bar.create_rectangle(x, 0, x + seg, 6, fill=THEME.accent, width=0, tags="sweep")
        except Exception:
            pass
        self._anim_job = self.after(16, self._animate_bar)

    # ── прогон ───────────────────────────────────────────────────────

    def _start_run(self) -> None:
        if self._running:
            return
        self._running = True
        self._cancelled = False
        self._best = None
        self._was_on = False
        try:
            self._was_on = self.ctl.is_on()
            if self._was_on:
                self._set_status("Останавливаю текущий обход…")
                self.ctl.stop()
        except Exception:
            log.exception("controller stop failed")
        self._animate_bar()
        self._set_status("Запускаю прогон стратегий…")

        cfg = self.ctl.cfg
        run_auto_select_async(
            on_progress=lambda s, sc, i, t: self.after(0, self._on_progress, s, sc, i, t),
            on_done=lambda scores, best: self.after(0, self._on_done, scores, best),
            should_stop=lambda: self._cancelled,
            custom_domains=list(cfg.get("custom_domains") or []),
            game_mode=str(cfg.get("game_mode", "normal")),
        )

    def _set_status(self, text: str) -> None:
        try:
            self._status.configure(text=text)
        except tk.TclError:
            pass

    def _on_progress(self, strategy: str, score: Optional[StrategyScore],
                     idx: int, total: int) -> None:
        if not self.winfo_exists():
            return
        row = self._rows.get(strategy)
        if score is None:
            self._set_status(f"Тестирую {self._short(strategy)}  ({idx + 1}/{total})…")
            if row:
                row["name"].configure(fg=THEME.text_primary)
                row["score"].configure(text="тест…", fg=THEME.accent)
            return
        if row:
            if score.error:
                row["score"].configure(text="ошибка", fg=THEME.danger)
            elif score.ok == 0:
                row["score"].configure(text=f"0/{score.total}", fg=THEME.text_muted)
            else:
                row["score"].configure(
                    text=f"{score.ok}/{score.total} · {score.avg_ms} ms",
                    fg=THEME.track_on if score.perfect else THEME.text_secondary,
                )
            row["name"].configure(fg=THEME.text_secondary)

    def _on_done(self, scores, best: Optional[StrategyScore]) -> None:
        if not self.winfo_exists():
            return
        self._running = False
        self._best = best or pick_best(scores or [])
        if self._cancelled:
            self._set_status("Подбор отменён.")
            self._restore_controller()
            return
        if self._best is None:
            self._set_status("Ни одна стратегия не открыла хосты. Проверьте сеть и логи.")
            self._restore_controller()
            return
        row = self._rows.get(self._best.strategy)
        if row:
            row["name"].configure(fg=THEME.track_on)
        self._set_status(
            f"Лучшая: {self._short(self._best.strategy)} — "
            f"{self._best.ok}/{self._best.total} хостов, {self._best.avg_ms} ms."
        )
        self._apply_btn.configure(fg=THEME.bg, bg=THEME.accent, cursor="hand2")
        self._apply_btn.bind("<Button-1>", lambda _e: self._apply())
        self._apply_btn.bind("<Enter>", lambda _e: self._apply_btn.configure(bg=THEME.accent_dim))
        self._apply_btn.bind("<Leave>", lambda _e: self._apply_btn.configure(bg=THEME.accent))
        self._cancel_btn.configure(text="  закрыть  ")

    def _restore_controller(self) -> None:
        if self._was_on:
            try:
                self.ctl.start()
            except Exception:
                log.exception("controller restart failed")
            self._was_on = False

    def _apply(self) -> None:
        if self._best is None:
            return
        try:
            self.ctl.update_cfg(
                zapret_strategy="auto",
                zapret_strategy_auto_result=self._best.strategy,
            )
        except Exception:
            log.exception("apply failed")
        if self._on_applied:
            try:
                self._on_applied(self._best.strategy)
            except Exception:
                log.exception("on_applied failed")
        self._restore_controller()
        self._close_now()

    def _close(self) -> None:
        if self._running:
            self._cancelled = True
            self._set_status("Отменяю после текущей стратегии…")
            return
        self._restore_controller()
        self._close_now()

    def _close_now(self) -> None:
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass
