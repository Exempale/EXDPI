"""Анимированный мастер первого запуска EXDPI.

Показывается один раз (cfg["wizard_done"] = False) и проводит пользователя
по шагам: приветствие → тема → домены → режим → стратегия (с авто-подбором)
→ опции → финиш.

Анимации без сторонних библиотек, на чистом Tk:
  * пульсирующие кольца вокруг логотипа на приветствии;
  * слайд-переходы между шагами (ease-out cubic, place());
  * «живые» точки прогресса внизу (активная растягивается в пилюлю);
  * прогресс-полоска во время авто-подбора стратегии;
  * прорисовывающаяся галочка на финальном шаге.

Результат отдаётся через ``on_finish(data: dict)`` — App сам мёржит в конфиг
и применяет (тема применяется живьём прямо из мастера).
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

from . import paths, presets
from .strategy_auto import StrategyScore, run_auto_select_async
from .theme import THEME, apply_theme, available_themes, label_for as theme_label_for


log = logging.getLogger("dpibypass.ui_wizard")

_EASE_STEPS = 18          # кадров на слайд-переход
_FRAME_MS = 14            # ~70 fps


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


class _MiniToggle(tk.Canvas):
    """Маленький переключатель (как в настройках), без зависимостей."""

    def __init__(self, master: tk.Misc, value: bool, bg: Optional[str] = None) -> None:
        super().__init__(master, width=44, height=22, bg=bg or THEME.bg,
                         highlightthickness=0, bd=0)
        self._on = bool(value)
        self.bind("<Button-1>", self._toggle)
        self.configure(cursor="hand2")
        self._draw()

    def get(self) -> bool:
        return self._on

    def _toggle(self, _e: tk.Event) -> None:
        self._on = not self._on
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        track = THEME.track_on if self._on else THEME.track_off
        knob = THEME.knob_on if self._on else THEME.knob_off
        self.create_oval(0, 0, 22, 22, fill=track, outline="")
        self.create_oval(22, 0, 44, 22, fill=track, outline="")
        self.create_rectangle(11, 0, 33, 22, fill=track, outline="")
        x = 24 if self._on else 2
        self.create_oval(x, 2, x + 18, 20, fill=knob, outline="")


class FirstRunWizard(tk.Toplevel):
    WIDTH = 640
    HEIGHT = 560

    STEP_COUNT = 7  # welcome, theme, domains, mode, strategy, options, finish

    def __init__(
        self,
        master: tk.Tk,
        cfg: Dict[str, Any],
        controller=None,
        on_finish: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        super().__init__(master)
        self.cfg = cfg
        self.ctl = controller
        self._on_finish = on_finish
        self._step = 0
        self._animating = False
        self._jobs: List[str] = []
        self._auto_running = False
        self._auto_done = False
        self._finished = False

        # выбранные значения (дефолты из конфига)
        self._data: Dict[str, Any] = {
            "theme": str(cfg.get("theme", "dark")),
            "domain_preset": str(cfg.get("domain_preset", "custom")) or "custom",
            "game_mode": str(cfg.get("game_mode", "normal")),
            "zapret_strategy": str(cfg.get("zapret_strategy", "general (ALT10).bat")),
            "zapret_strategy_auto_result": str(cfg.get("zapret_strategy_auto_result", "")),
            "autostart_with_windows": bool(cfg.get("autostart_with_windows", False)),
            "minimize_to_tray": bool(cfg.get("minimize_to_tray", True)),
            "notifications_enabled": bool(cfg.get("notifications_enabled", True)),
            "securedns_enabled": bool(cfg.get("securedns_enabled", False)),
            "wizard_done": True,
        }
        self._strategy_choice = tk.StringVar(value="auto")

        self.title("EXDPI · первый запуск")
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
        self.protocol("WM_DELETE_WINDOW", self._skip_all)

    # ── базовая раскладка ────────────────────────────────────────────

    def _center(self, master: tk.Misc) -> None:
        self.update_idletasks()
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            x = mx + (mw - self.WIDTH) // 2
            y = my + (mh - self.HEIGHT) // 2
            x = max(10, min(x, sw - self.WIDTH - 10))
            y = max(10, min(y, sh - self.HEIGHT - 60))
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        except Exception:
            self.geometry(f"{self.WIDTH}x{self.HEIGHT}")

    def _after(self, ms: int, fn, *args) -> None:
        try:
            self._jobs.append(self.after(ms, fn, *args))
        except Exception:
            pass

    def _build(self) -> None:
        self.configure(bg=THEME.bg)
        for w in self.winfo_children():
            w.destroy()

        outer = tk.Frame(self, bg=THEME.bg)
        outer.pack(fill="both", expand=True)

        # контейнер шагов (фиксированная зона для слайдов)
        self._stage = tk.Frame(outer, bg=THEME.bg)
        self._stage.pack(side="top", fill="both", expand=True)
        self._stage.pack_propagate(False)

        # низ: точки прогресса + кнопки
        bottom = tk.Frame(outer, bg=THEME.bg, padx=26, pady=16)
        bottom.pack(side="bottom", fill="x")

        self._dots = tk.Canvas(bottom, height=10, width=140, bg=THEME.bg,
                               highlightthickness=0, bd=0)
        self._dots.pack(side="left")

        self._next_btn = tk.Label(
            bottom, text="  далее  →  ",
            fg=THEME.bg, bg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"),
            cursor="hand2", padx=16, pady=8,
        )
        self._next_btn.pack(side="right")
        self._next_btn.bind("<Button-1>", lambda _e: self._next())
        self._next_btn.bind("<Enter>", lambda _e: self._next_btn.configure(bg=THEME.accent_dim))
        self._next_btn.bind("<Leave>", lambda _e: self._next_btn.configure(bg=THEME.accent))

        self._back_btn = tk.Label(
            bottom, text="←  назад",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 10), cursor="hand2", padx=8, pady=8,
        )
        self._back_btn.pack(side="right", padx=(0, 8))
        self._back_btn.bind("<Button-1>", lambda _e: self._back())

        self._skip_btn = tk.Label(
            bottom, text="пропустить",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"), cursor="hand2",
        )
        self._skip_btn.pack(side="right", padx=(0, 14))
        self._skip_btn.bind("<Button-1>", lambda _e: self._skip_all())

        # создаём фрейм текущего шага
        self._current_frame = self._make_step(self._step)
        self._current_frame.place(x=0, y=0, relwidth=1, relheight=1)
        self._draw_dots(float(self._step))
        self._update_buttons()
        if self._step == 0:
            self._start_pulse()

    # ── точки прогресса ──────────────────────────────────────────────

    def _draw_dots(self, pos: float) -> None:
        """pos — дробный индекс активного шага (для анимации перетекания)."""
        cv = self._dots
        try:
            cv.delete("all")
        except tk.TclError:
            return
        n = self.STEP_COUNT
        r = 3
        gap = 18
        y = 5
        for i in range(n):
            x = 8 + i * gap
            # близость к активной позиции 0..1
            d = max(0.0, 1.0 - abs(pos - i))
            if d > 0.02:
                # активная точка растягивается в пилюлю
                w = r + d * 7
                color = THEME.accent
                cv.create_oval(x - w, y - r, x + w, y + r, fill=color, outline="")
            else:
                cv.create_oval(x - r, y - r, x + r, y + r, fill=THEME.border, outline="")

    def _update_buttons(self) -> None:
        try:
            if self._step == 0:
                self._back_btn.pack_forget()
                self._next_btn.configure(text="  начать  →  ")
            elif self._step == self.STEP_COUNT - 1:
                self._back_btn.pack_forget()
                self._skip_btn.pack_forget()
                self._next_btn.configure(text="  готово  ✓  ")
            else:
                self._back_btn.pack(side="right", padx=(0, 8))
                self._next_btn.configure(text="  далее  →  ")
        except tk.TclError:
            pass

    # ── навигация со слайдом ─────────────────────────────────────────

    def _next(self) -> None:
        if self._animating or self._finished:
            return
        if self._step == 4 and self._strategy_choice.get() == "auto" and not self._auto_done:
            self._run_auto_strategy()
            return
        if self._step >= self.STEP_COUNT - 1:
            self._finish()
            return
        self._slide_to(self._step + 1, direction=1)

    def _back(self) -> None:
        if self._animating or self._step <= 0 or self._finished:
            return
        self._slide_to(self._step - 1, direction=-1)

    def _slide_to(self, new_step: int, direction: int) -> None:
        self._animating = True
        old_frame = self._current_frame
        old_step = self._step
        self._step = new_step
        new_frame = self._make_step(new_step)
        w = max(self._stage.winfo_width(), 1)
        new_frame.place(x=direction * w, y=0, relwidth=1, relheight=1)
        self._update_buttons()

        frames = _EASE_STEPS

        def _tick(i: int) -> None:
            t = _ease_out_cubic(i / frames)
            try:
                old_frame.place_configure(x=int(-direction * w * t))
                new_frame.place_configure(x=int(direction * w * (1 - t)))
                self._draw_dots(old_step + (new_step - old_step) * t)
            except tk.TclError:
                return
            if i < frames:
                self._after(_FRAME_MS, _tick, i + 1)
            else:
                try:
                    old_frame.destroy()
                except Exception:
                    pass
                self._current_frame = new_frame
                self._animating = False
                self._draw_dots(float(new_step))
                if new_step == 0:
                    self._start_pulse()
                if new_step == self.STEP_COUNT - 1:
                    self._start_checkmark()

        _tick(1)

    # ── шаги ─────────────────────────────────────────────────────────

    def _make_step(self, idx: int) -> tk.Frame:
        builders = [
            self._step_welcome, self._step_theme, self._step_domains,
            self._step_mode, self._step_strategy, self._step_options,
            self._step_finish,
        ]
        frame = tk.Frame(self._stage, bg=THEME.bg)
        try:
            builders[idx](frame)
        except Exception:
            log.exception("wizard step %d build failed", idx)
        return frame

    def _heading(self, frame: tk.Frame, kicker: str, title: str, subtitle: str) -> None:
        box = tk.Frame(frame, bg=THEME.bg, padx=30, pady=24)
        box.pack(fill="x")
        tk.Label(box, text=kicker.upper(), fg=THEME.accent_dim, bg=THEME.bg,
                 font=(THEME.font_ui, 8, "bold"), anchor="w").pack(fill="x")
        tk.Label(box, text=title, fg=THEME.text_primary, bg=THEME.bg,
                 font=(THEME.font_ui, 16, "bold"), anchor="w").pack(fill="x", pady=(2, 0))
        if subtitle:
            tk.Label(box, text=subtitle, fg=THEME.text_secondary, bg=THEME.bg,
                     font=(THEME.font_ui, 10), anchor="w",
                     wraplength=560, justify="left").pack(fill="x", pady=(6, 0))

    # 0 — приветствие
    def _step_welcome(self, frame: tk.Frame) -> None:
        center = tk.Frame(frame, bg=THEME.bg)
        center.pack(expand=True)

        self._pulse_cv = tk.Canvas(center, width=170, height=170, bg=THEME.bg,
                                   highlightthickness=0, bd=0)
        self._pulse_cv.pack(pady=(22, 8))

        self._welcome_title = tk.Label(
            center, text="Добро пожаловать в EXDPI",
            fg=THEME.bg, bg=THEME.bg,  # появится через fade-in
            font=(THEME.font_ui, 18, "bold"),
        )
        self._welcome_title.pack()
        self._welcome_sub = tk.Label(
            center,
            text="Обход DPI-блокировок, Telegram-прокси и защищённый DNS.\n"
                 "Сейчас всё настроим за минуту.",
            fg=THEME.bg, bg=THEME.bg,
            font=(THEME.font_ui, 10), justify="center",
        )
        self._welcome_sub.pack(pady=(8, 18))
        self._after(150, self._fade_in_welcome, 0)

    @staticmethod
    def _mix(c1: str, c2: str, t: float) -> str:
        def rgb(c: str):
            c = c.lstrip("#")
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        a, b = rgb(c1), rgb(c2)
        return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def _fade_in_welcome(self, i: int) -> None:
        steps = 22
        t = _ease_out_cubic(min(1.0, i / steps))
        try:
            self._welcome_title.configure(fg=self._mix(THEME.bg, THEME.text_primary, t))
            self._welcome_sub.configure(fg=self._mix(THEME.bg, THEME.text_secondary, max(0.0, t - 0.25) / 0.75))
        except tk.TclError:
            return
        if i < steps:
            self._after(28, self._fade_in_welcome, i + 1)

    def _start_pulse(self) -> None:
        self._pulse_phase = 0.0
        self._pulse_tick()

    def _pulse_tick(self) -> None:
        if self._step != 0 or self._finished:
            return
        cv = getattr(self, "_pulse_cv", None)
        if cv is None:
            return
        try:
            cv.delete("all")
            cx = cy = 85
            self._pulse_phase = (self._pulse_phase + 0.012) % 1.0
            # два расходящихся кольца
            for k in (0.0, 0.5):
                p = (self._pulse_phase + k) % 1.0
                r = 34 + p * 46
                color = self._mix(THEME.accent, THEME.bg, p)
                cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2)
            # ядро-логотип
            cv.create_oval(cx - 34, cy - 34, cx + 34, cy + 34,
                           fill=THEME.card, outline=THEME.accent, width=2)
            cv.create_text(cx, cy, text="EX", fill=THEME.accent,
                           font=(THEME.font_ui, 17, "bold"))
        except tk.TclError:
            return
        self._after(30, self._pulse_tick)

    # карточка-вариант (используется в нескольких шагах)
    def _card_option(self, master: tk.Frame, title: str, subtitle: str,
                     selected: Callable[[], bool], on_click: Callable[[], None]) -> tk.Frame:
        card = tk.Frame(master, bg=THEME.card, padx=16, pady=12,
                        highlightthickness=1, highlightbackground=THEME.border)
        title_lbl = tk.Label(card, text=title, fg=THEME.text_primary, bg=THEME.card,
                             font=(THEME.font_ui, 11, "bold"), anchor="w")
        title_lbl.pack(fill="x")
        sub_lbl = tk.Label(card, text=subtitle, fg=THEME.text_secondary, bg=THEME.card,
                           font=(THEME.font_ui, 9), anchor="w", wraplength=520, justify="left")
        sub_lbl.pack(fill="x", pady=(2, 0))

        def _refresh_all() -> None:
            for c, sel in getattr(master, "_cards", []):
                try:
                    c.configure(highlightbackground=THEME.accent if sel() else THEME.border,
                                highlightthickness=2 if sel() else 1)
                except tk.TclError:
                    pass

        def _click(_e: tk.Event) -> None:
            on_click()
            _refresh_all()

        for w in (card, title_lbl, sub_lbl):
            w.bind("<Button-1>", _click)
            w.configure(cursor="hand2")

        if not hasattr(master, "_cards"):
            master._cards = []  # type: ignore[attr-defined]
        master._cards.append((card, selected))  # type: ignore[attr-defined]
        _refresh_all()
        return card

    # 1 — тема
    def _step_theme(self, frame: tk.Frame) -> None:
        self._heading(frame, "шаг 1 · оформление", "Выберите тему",
                      "Применяется сразу. Потом можно переключить в один клик из главного окна.")
        box = tk.Frame(frame, bg=THEME.bg, padx=30)
        box.pack(fill="x")
        for name in available_themes():
            card = self._card_option(
                box,
                theme_label_for(name),
                "Мягкий тёмный интерфейс — глазам приятно ночью."
                if name == "dark" else "Светлый и контрастный — для яркого дня.",
                selected=lambda n=name: self._data["theme"] == n,
                on_click=lambda n=name: self._pick_theme(n),
            )
            card.pack(fill="x", pady=(0, 10))

    def _pick_theme(self, name: str) -> None:
        if self._data["theme"] == name:
            return
        self._data["theme"] = name
        apply_theme(name)
        # пересобрать мастер в новой палитре, остаёмся на том же шаге
        self._build()

    # 2 — домены
    def _step_domains(self, frame: tk.Frame) -> None:
        self._heading(frame, "шаг 2 · домены", "Что разблокируем?",
                      "Готовый набор доменов для обхода. Свои домены можно добавить "
                      "позже в настройках.")
        box = tk.Frame(frame, bg=THEME.bg, padx=30)
        box.pack(fill="x")
        for p in presets.presets():
            desc = p.description if p.id != "custom" else \
                "Пустой список — добавите свои домены в настройках."
            card = self._card_option(
                box, p.label, desc,
                selected=lambda pid=p.id: self._data["domain_preset"] == pid,
                on_click=lambda pid=p.id: self._data.__setitem__("domain_preset", pid),
            )
            card.pack(fill="x", pady=(0, 8))

    # 3 — режим
    def _step_mode(self, frame: tk.Frame) -> None:
        self._heading(frame, "шаг 3 · режим", "Режим обхода",
                      "Можно поменять в любой момент в настройках или из трея.")
        box = tk.Frame(frame, bg=THEME.bg, padx=30)
        box.pack(fill="x")
        options = (
            ("normal", "Обычный",
             "Фильтруются стандартные TLS/HTTP/QUIC порты. Подходит большинству."),
            ("gaming", "Гейминг",
             "GameFilter 1024-65535 для TCP+UDP: голос Discord, игровые лобби, P2P."),
        )
        for mode_id, title, desc in options:
            card = self._card_option(
                box, title, desc,
                selected=lambda m=mode_id: self._data["game_mode"] == m,
                on_click=lambda m=mode_id: self._data.__setitem__("game_mode", m),
            )
            card.pack(fill="x", pady=(0, 10))

    # 4 — стратегия
    def _step_strategy(self, frame: tk.Frame) -> None:
        self._heading(frame, "шаг 4 · стратегия", "Стратегия zapret",
                      "«Авто» прогонит все стратегии и выберет ту, что реально "
                      "пробивает блокировки у вашего провайдера (~1-2 минуты).")
        box = tk.Frame(frame, bg=THEME.bg, padx=30)
        box.pack(fill="x")

        card_auto = self._card_option(
            box, "Авто-подбор  ·  рекомендуется",
            "Запустим каждую стратегию и измерим, сколько заблокированных хостов "
            "она открывает. Начнётся по кнопке «далее».",
            selected=lambda: self._strategy_choice.get() == "auto",
            on_click=lambda: self._strategy_choice.set("auto"),
        )
        card_auto.pack(fill="x", pady=(0, 10))

        card_def = self._card_option(
            box, "Стандартная (ALT10)",
            "Проверенная стратегия по умолчанию. Авто-подбор можно запустить "
            "позже из настроек.",
            selected=lambda: self._strategy_choice.get() == "default",
            on_click=lambda: self._strategy_choice.set("default"),
        )
        card_def.pack(fill="x", pady=(0, 10))

        # зона прогресса авто-подбора
        self._auto_bar = tk.Canvas(box, height=4, bg=THEME.card,
                                   highlightthickness=0, bd=0)
        self._auto_status = tk.Label(
            box, text="", fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9), anchor="w",
        )
        if self._auto_running or self._auto_done:
            self._auto_bar.pack(fill="x", pady=(4, 0))
            self._auto_status.pack(fill="x", pady=(6, 0))
            if self._auto_done:
                self._auto_status.configure(text=self._auto_result_text(), fg=THEME.track_on)

    def _auto_result_text(self) -> str:
        res = self._data.get("zapret_strategy_auto_result") or ""
        if not res:
            return "Авто-подбор не дал результата — будет стандартная стратегия."
        short = res[:-4] if res.endswith(".bat") else res
        return f"Выбрана: {short} ✓"

    def _run_auto_strategy(self) -> None:
        if self._auto_running:
            return
        self._auto_running = True
        try:
            self._auto_bar.pack(fill="x", pady=(4, 0))
            self._auto_status.pack(fill="x", pady=(6, 0))
            self._auto_status.configure(text="Готовлю прогон…", fg=THEME.text_secondary)
            self._next_btn.configure(text="  подбираю…  ")
        except tk.TclError:
            pass

        # на всякий случай гасим обход (WinDivert-фильтр один на систему)
        try:
            if self.ctl is not None and self.ctl.is_on():
                self.ctl.stop()
        except Exception:
            log.exception("controller stop failed before auto-select")

        self._auto_anim_phase = 0.0
        self._animate_auto_bar()

        cfg = self.ctl.cfg if self.ctl is not None else self.cfg
        domains = presets.load_domains(self._data["domain_preset"]) or \
            list(cfg.get("custom_domains") or [])
        run_auto_select_async(
            on_progress=lambda s, sc, i, t: self.after(0, self._auto_progress, s, sc, i, t),
            on_done=lambda scores, best: self.after(0, self._auto_finished, best),
            should_stop=lambda: self._finished,
            custom_domains=domains,
            game_mode=str(self._data["game_mode"]),
        )

    def _animate_auto_bar(self) -> None:
        if not self._auto_running or self._finished:
            return
        try:
            w = max(self._auto_bar.winfo_width(), 1)
            self._auto_bar.delete("sweep")
            seg = max(60, w // 4)
            self._auto_anim_phase = (self._auto_anim_phase + 0.02) % 1.0
            x = int(self._auto_anim_phase * (w + seg)) - seg
            self._auto_bar.create_rectangle(x, 0, x + seg, 6, fill=THEME.accent,
                                            width=0, tags="sweep")
        except tk.TclError:
            return
        self._after(16, self._animate_auto_bar)

    def _auto_progress(self, strategy: str, score: Optional[StrategyScore],
                       idx: int, total: int) -> None:
        if self._finished:
            return
        try:
            if score is None:
                short = strategy[:-4] if strategy.endswith(".bat") else strategy
                self._auto_status.configure(text=f"Тестирую {short}  ({idx + 1}/{total})…")
            elif score.ok:
                self._auto_status.configure(
                    text=f"{strategy[:-4] if strategy.endswith('.bat') else strategy}: "
                         f"{score.ok}/{score.total} хостов, {score.avg_ms} ms")
        except tk.TclError:
            pass

    def _auto_finished(self, best: Optional[StrategyScore]) -> None:
        self._auto_running = False
        self._auto_done = True
        if best is not None:
            self._data["zapret_strategy"] = "auto"
            self._data["zapret_strategy_auto_result"] = best.strategy
        else:
            self._data["zapret_strategy"] = "general (ALT10).bat"
            self._data["zapret_strategy_auto_result"] = ""
        try:
            self._auto_bar.delete("sweep")
            self._auto_status.configure(text=self._auto_result_text(),
                                        fg=THEME.track_on if best else THEME.danger)
            self._next_btn.configure(text="  далее  →  ")
        except tk.TclError:
            pass
        if self._finished:
            return
        # автоматически едем дальше через секунду
        self._after(1100, self._advance_after_auto)

    def _advance_after_auto(self) -> None:
        if self._step == 4 and not self._animating and not self._finished:
            self._slide_to(5, direction=1)

    # 5 — опции
    def _step_options(self, frame: tk.Frame) -> None:
        self._heading(frame, "шаг 5 · опции", "Последние штрихи",
                      "Всё это можно поменять в настройках в любой момент.")
        box = tk.Frame(frame, bg=THEME.bg, padx=30)
        box.pack(fill="x")

        self._opt_toggles: Dict[str, _MiniToggle] = {}
        options = (
            ("autostart_with_windows", "Запускать с Windows",
             "EXDPI стартует вместе с системой (HKCU\\…\\Run)."),
            ("minimize_to_tray", "Сворачивать в трей",
             "По крестику окно прячется в трей, обход продолжает работать."),
            ("notifications_enabled", "Уведомления Windows",
             "Тосты о включении/выключении обхода и ошибках."),
            ("securedns_enabled", "Защищённый DNS (DoH)",
             "Локальный DNS-резолвер: запросы шифруются до Cloudflare, "
             "провайдер не видит и не подменяет их."),
        )
        for key, title, desc in options:
            row = tk.Frame(box, bg=THEME.bg, pady=6)
            row.pack(fill="x")
            left = tk.Frame(row, bg=THEME.bg)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=title, fg=THEME.text_primary, bg=THEME.bg,
                     font=(THEME.font_ui, 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(left, text=desc, fg=THEME.text_secondary, bg=THEME.bg,
                     font=(THEME.font_ui, 9), anchor="w",
                     wraplength=470, justify="left").pack(fill="x")
            toggle = _MiniToggle(row, bool(self._data[key]))
            toggle.pack(side="right", padx=(10, 0))
            self._opt_toggles[key] = toggle

    def _collect_options(self) -> None:
        for key, toggle in getattr(self, "_opt_toggles", {}).items():
            try:
                self._data[key] = bool(toggle.get())
            except Exception:
                pass

    # 6 — финиш
    def _step_finish(self, frame: tk.Frame) -> None:
        self._collect_options()
        center = tk.Frame(frame, bg=THEME.bg)
        center.pack(expand=True)
        self._check_cv = tk.Canvas(center, width=120, height=120, bg=THEME.bg,
                                   highlightthickness=0, bd=0)
        self._check_cv.pack(pady=(20, 10))
        tk.Label(center, text="Всё готово!", fg=THEME.text_primary, bg=THEME.bg,
                 font=(THEME.font_ui, 17, "bold")).pack()

        strategy = self._data.get("zapret_strategy", "")
        if strategy == "auto" and self._data.get("zapret_strategy_auto_result"):
            res = self._data["zapret_strategy_auto_result"]
            s_text = f"Авто ({res[:-4] if res.endswith('.bat') else res})"
        elif strategy == "auto":
            s_text = "Авто"
        else:
            s_text = strategy[:-4] if strategy.endswith(".bat") else strategy
        preset = presets.by_id(self._data["domain_preset"])
        summary = (
            f"Тема: {theme_label_for(self._data['theme'])}   ·   "
            f"Домены: {preset.label if preset else '—'}\n"
            f"Режим: {'гейминг' if self._data['game_mode'] == 'gaming' else 'обычный'}"
            f"   ·   Стратегия: {s_text}"
        )
        tk.Label(center, text=summary, fg=THEME.text_secondary, bg=THEME.bg,
                 font=(THEME.font_ui, 10), justify="center").pack(pady=(10, 4))
        tk.Label(center, text="Нажмите «готово» и включайте большой переключатель.",
                 fg=THEME.text_muted, bg=THEME.bg,
                 font=(THEME.font_ui, 9), justify="center").pack()

    def _start_checkmark(self) -> None:
        cv = getattr(self, "_check_cv", None)
        if cv is None:
            return
        # точки галочки внутри круга 120×120
        pts = [(34, 62), (53, 81), (88, 42)]

        def _tick(i: int) -> None:
            steps = 26
            t = _ease_out_cubic(min(1.0, i / steps))
            try:
                cv.delete("all")
                # круг рисуется дугой
                extent = -359.9 * min(1.0, t * 1.4)
                cv.create_arc(8, 8, 112, 112, start=90, extent=extent,
                              style="arc", outline=THEME.accent, width=3)
                # галочка — после половины анимации
                ct = max(0.0, (t - 0.45) / 0.55)
                if ct > 0:
                    path: List[float] = [pts[0][0], pts[0][1]]
                    total_seg = 2
                    prog = ct * total_seg
                    for seg in range(1, 3):
                        if prog >= seg:
                            path += [pts[seg][0], pts[seg][1]]
                        elif prog > seg - 1:
                            f = prog - (seg - 1)
                            x = pts[seg - 1][0] + (pts[seg][0] - pts[seg - 1][0]) * f
                            y = pts[seg - 1][1] + (pts[seg][1] - pts[seg - 1][1]) * f
                            path += [x, y]
                            break
                    if len(path) >= 4:
                        cv.create_line(*path, fill=THEME.accent, width=5,
                                       capstyle="round", joinstyle="round")
            except tk.TclError:
                return
            if i < steps:
                self._after(24, _tick, i + 1)

        _tick(1)

    # ── завершение ───────────────────────────────────────────────────

    def _result_data(self) -> Dict[str, Any]:
        self._collect_options()
        data = dict(self._data)
        # домены из пресета (custom — не трогаем пользовательский список)
        if data["domain_preset"] != "custom":
            domains = presets.load_domains(data["domain_preset"])
            if domains:
                data["custom_domains"] = domains
        if self._strategy_choice.get() == "default" or (
            data["zapret_strategy"] == "auto" and not data["zapret_strategy_auto_result"]
        ):
            data["zapret_strategy"] = "general (ALT10).bat"
        return data

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        data = self._result_data()
        self._close()
        if self._on_finish:
            try:
                self._on_finish(data)
            except Exception:
                log.exception("wizard on_finish failed")

    def _skip_all(self) -> None:
        """Закрыть мастер — отмечаем wizard_done, чтобы не надоедать."""
        if self._finished:
            return
        self._finished = True
        data = {"wizard_done": True}
        # тему пользователь мог уже переключить — сохраняем
        data["theme"] = self._data["theme"]
        self._close()
        if self._on_finish:
            try:
                self._on_finish(data)
            except Exception:
                log.exception("wizard on_finish failed")

    def _close(self) -> None:
        for j in self._jobs:
            try:
                self.after_cancel(j)
            except Exception:
                pass
        self._jobs = []
        try:
            self.destroy()
        except Exception:
            pass
