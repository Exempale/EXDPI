"""Кастомные виджеты: гладкий тоггл, иконки, бейдж статуса."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

from . import countries
from .theme import THEME


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _hex_to_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        int(round(_lerp(r1, r2, t))),
        int(round(_lerp(g1, g2, t))),
        int(round(_lerp(b1, b2, t))),
    )


def _ease_in_out(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


class AnimatedToggle(tk.Canvas):
    """Большой стилизованный тоггл с плавной анимацией.

    Не использует customtkinter — рисуется вручную на Canvas, чтобы
    результат выглядел одинаково на всех системах и идеально подходил
    под минималистичную тёмную тему.
    """

    WIDTH = 168
    HEIGHT = 64
    KNOB_PAD = 6

    def __init__(self, master: tk.Misc, on_change: Optional[Callable[[bool], None]] = None) -> None:
        super().__init__(
            master,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=THEME.bg,
            highlightthickness=0,
            bd=0,
        )
        self._on_change = on_change
        self._state = False
        self._anim = 0.0
        self._target = 0.0
        self._anim_job: Optional[str] = None
        self._busy = False

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._draw()

    def _on_enter(self, _e: tk.Event) -> None:
        if not self._busy:
            self.configure(cursor="hand2")

    def _on_leave(self, _e: tk.Event) -> None:
        self.configure(cursor="" if not self._busy else "watch")

    # ── public API ──────────────────────────────────────────────────────
    def get(self) -> bool:
        return self._state

    def set(self, value: bool, *, fire: bool = False, animate: bool = True) -> None:
        new_state = bool(value)
        same = (new_state == self._state)
        self._state = new_state
        self._target = 1.0 if self._state else 0.0
        if not animate:
            self._anim = self._target
            self._draw()
        elif not same:
            self._tick()
        else:
            self._draw()
        if fire and self._on_change:
            self._on_change(self._state)

    def set_busy(self, busy: bool) -> None:
        # не используем state="disabled" у Canvas — с ним items рендерятся
        # пустыми; вместо этого блокируем обработчик клика самостоятельно.
        self._busy = bool(busy)
        self.configure(cursor="watch" if busy else "")
        self._draw()

    # ── internal ────────────────────────────────────────────────────────
    def _on_click(self, _evt: tk.Event) -> None:
        if getattr(self, "_busy", False):
            return
        self._state = not self._state
        self._target = 1.0 if self._state else 0.0
        self._tick()
        if self._on_change:
            self._on_change(self._state)

    def _tick(self) -> None:
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

        diff = self._target - self._anim
        step = 0.10 if abs(diff) > 0.01 else diff
        self._anim += step
        self._draw()
        if abs(self._target - self._anim) > 0.005:
            self._anim_job = self.after(12, self._tick)
        else:
            self._anim = self._target
            self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = self.WIDTH, self.HEIGHT
        t = _ease_in_out(self._anim)

        track = _mix(THEME.track_off, THEME.track_on, t)
        knob = _mix(THEME.knob_off, THEME.knob_on, t)

        # track
        r = h // 2
        self._round_rect(0, 0, w, h, r, fill=track, outline="")

        # светящийся обвод, когда включено
        if t > 0.05:
            glow_color = _mix(THEME.bg, THEME.track_on, 0.5)
            self._round_rect(
                -1, -1, w + 1, h + 1, r + 1,
                fill="", outline=glow_color, width=1,
            )
        # subtle inner gradient
        inner = _mix(track, "#000000", 0.22)
        self._round_rect(2, 2, w - 2, h - 2, r - 2, fill="", outline=inner, width=1)

        # OFF / ON label вырисовываем в свободной части трека,
        # чтобы он не перекрывался кнопкой
        if self._state:
            text = "ON"
            tx = self.KNOB_PAD + 22
            tcolor = _mix(THEME.knob_on, THEME.bg, 0.55)
        else:
            text = "OFF"
            tx = w - self.KNOB_PAD - 26
            tcolor = _mix(THEME.knob_off, THEME.text_secondary, 0.4)
        self.create_text(
            tx, h // 2,
            text=text,
            fill=tcolor,
            font=(THEME.font_ui, 11, "bold"),
        )

        # knob — рисуем поверх текста
        knob_d = h - self.KNOB_PAD * 2
        x = self.KNOB_PAD + (w - knob_d - self.KNOB_PAD * 2) * t
        y = self.KNOB_PAD
        # shadow
        self.create_oval(x + 1, y + 2, x + knob_d + 1, y + knob_d + 2,
                         fill="#000000", outline="", stipple="gray25")
        self.create_oval(x, y, x + knob_d, y + knob_d, fill=knob, outline="")
        # knob highlight
        hi = _mix(knob, "#ffffff", 0.22)
        self.create_oval(x + 4, y + 3, x + knob_d - 6, y + knob_d - 14,
                         fill=hi, outline="")

        if self._busy:
            # лёгкая полупрозрачная плёнка поверх
            self._round_rect(0, 0, w, h, r, fill="#000000",
                             outline="", stipple="gray25")

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(pts, smooth=True, **kw)


class StatusDot(tk.Canvas):
    """Маленький светящийся индикатор."""

    SIZE = 12

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(
            master,
            width=self.SIZE,
            height=self.SIZE,
            bg=THEME.bg,
            highlightthickness=0,
            bd=0,
        )
        self._color = THEME.danger
        self._draw()

    def set_color(self, color: str) -> None:
        if color != self._color:
            self._color = color
            self._draw()

    def _draw(self) -> None:
        self.delete("all")
        s = self.SIZE
        glow = _mix(THEME.bg, self._color, 0.4)
        self.create_oval(0, 0, s, s, fill=glow, outline="")
        self.create_oval(2, 2, s - 2, s - 2, fill=self._color, outline="")


class IconButton(tk.Canvas):
    """Минималистичная иконка-кнопка (рисуется вручную)."""

    def __init__(
        self,
        master: tk.Misc,
        glyph: str,
        size: int = 28,
        on_click: Optional[Callable[[], None]] = None,
        tooltip: str = "",
    ) -> None:
        super().__init__(
            master,
            width=size,
            height=size,
            bg=THEME.bg,
            highlightthickness=0,
            bd=0,
        )
        self._size = size
        self._glyph = glyph
        self._hover = False
        self._on_click = on_click
        self._tooltip = tooltip
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self._draw()

    def set_bg(self, color: str) -> None:
        self.configure(bg=color)
        self._draw()

    def _enter(self, _e: tk.Event) -> None:
        self._hover = True
        self.configure(cursor="hand2")
        self._draw()

    def _leave(self, _e: tk.Event) -> None:
        self._hover = False
        self.configure(cursor="")
        self._draw()

    def _click(self, _e: tk.Event) -> None:
        if self._on_click:
            self._on_click()

    def _draw(self) -> None:
        self.delete("all")
        s = self._size
        bg = str(self.cget("bg"))
        if self._hover:
            self.create_oval(0, 0, s, s, fill=THEME.card, outline="")
        color = THEME.text_primary if self._hover else THEME.text_secondary

        if self._glyph == "gear":
            self._draw_gear(s, color)
        elif self._glyph == "copy":
            self._draw_copy(s, color)
        elif self._glyph == "back":
            self._draw_back(s, color)
        elif self._glyph == "check":
            self._draw_check(s, color)
        elif self._glyph == "theme":
            self._draw_theme(s, color)
        else:
            self.create_text(s // 2, s // 2, text=self._glyph,
                             fill=color, font=(THEME.font_ui, int(s * 0.55)))

    def _draw_gear(self, s: int, color: str) -> None:
        # компактная иконка-шестерёнка: тело-кольцо + 8 равномерных "зубцов"
        # и круглая дырка по центру. Помещается в холст с отступом.
        cx = cy = s / 2
        body_outer = s * 0.34
        body_inner = s * 0.18
        tooth_outer = s * 0.44
        tooth_w = s * 0.10
        teeth = 8

        # зубцы — короткие прямоугольники, "торчащие" из тела
        for i in range(teeth):
            ang = (i / teeth) * 2 * math.pi
            ca, sa = math.cos(ang), math.sin(ang)
            # центр зубца на расстоянии (body_outer + tooth_outer)/2
            mid = (body_outer + tooth_outer) / 2
            tx, ty = cx + ca * mid, cy + sa * mid
            half_l = (tooth_outer - body_outer) / 2 + 0.5
            half_w = tooth_w / 2
            # ось вдоль (ca, sa); поперёк — (-sa, ca)
            ax, ay = ca * half_l, sa * half_l
            bx, by = -sa * half_w, ca * half_w
            pts = [
                tx - ax - bx, ty - ay - by,
                tx + ax - bx, ty + ay - by,
                tx + ax + bx, ty + ay + by,
                tx - ax + bx, ty - ay + by,
            ]
            self.create_polygon(pts, fill=color, outline="")

        # тело шестерёнки
        self.create_oval(cx - body_outer, cy - body_outer,
                         cx + body_outer, cy + body_outer,
                         fill=color, outline="")
        # дырка по центру
        self.create_oval(cx - body_inner, cy - body_inner,
                         cx + body_inner, cy + body_inner,
                         fill=str(self.cget("bg")), outline="")

    def _draw_copy(self, s: int, color: str) -> None:
        # two overlapping rounded squares
        a = s * 0.25
        b = s * 0.62
        pad = s * 0.16
        # back square
        self._rect(self, pad + a * 0.4, pad + a * 0.4,
                   pad + a * 0.4 + b, pad + a * 0.4 + b,
                   r=3, outline=color, width=1.6)
        # front square (filled bg to overlap)
        self._rect(self, pad, pad, pad + b, pad + b,
                   r=3, outline=color, width=1.6,
                   fill=str(self.cget("bg")))

    def _draw_back(self, s: int, color: str) -> None:
        pad = s * 0.32
        self.create_line(s - pad, pad, pad, s / 2, fill=color, width=2,
                         capstyle="round")
        self.create_line(pad, s / 2, s - pad, s - pad, fill=color, width=2,
                         capstyle="round")

    def _draw_check(self, s: int, color: str) -> None:
        pad = s * 0.25
        self.create_line(pad, s / 2, s * 0.45, s - pad, fill=color, width=2,
                         capstyle="round")
        self.create_line(s * 0.45, s - pad, s - pad, pad, fill=color, width=2,
                         capstyle="round")

    def _draw_theme(self, s: int, color: str) -> None:
        """Иконка переключения темы: солнце для светлой, луна для тёмной.

        Глиф зависит от текущей THEME.name — пользователь видит, на какую
        тему он переключится. Светлая тема: солнце с лучами; тёмная: луна
        (полумесяц).
        """
        import math as _m
        bg = str(self.cget("bg"))
        cx = cy = s / 2

        if THEME.name == "dark":
            # рисуем солнышко — намёк, что клик переключит на светлую
            body_r = s * 0.22
            ray_in = s * 0.30
            ray_out = s * 0.42
            for i in range(8):
                ang = i * (2 * _m.pi / 8)
                ca, sa = _m.cos(ang), _m.sin(ang)
                self.create_line(
                    cx + ca * ray_in, cy + sa * ray_in,
                    cx + ca * ray_out, cy + sa * ray_out,
                    fill=color, width=2, capstyle="round",
                )
            self.create_oval(
                cx - body_r, cy - body_r, cx + body_r, cy + body_r,
                fill=color, outline="",
            )
        else:
            # рисуем луну — клик переключит на тёмную
            r = s * 0.34
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             fill=color, outline="")
            # вырезаем фоновым кругом — получается полумесяц
            cut = s * 0.30
            self.create_oval(
                cx - r + cut * 0.6, cy - r - cut * 0.1,
                cx + r + cut * 0.6, cy + r - cut * 0.1,
                fill=bg, outline="",
            )

    @staticmethod
    def _rect(canvas: tk.Canvas, x1, y1, x2, y2, r=4, **kw) -> None:
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        canvas.create_polygon(pts, smooth=True, **kw)


class AppModeSwitch(tk.Frame):
    """Компактный сегментный переключатель [ DPI | VPN ] для header.

    Используется на главном экране: клик по сегменту меняет режим
    приложения (DPI-обход ↔ VPN через Sing-box). Стилизован под THEME —
    активный сегмент рисуется акцентным цветом, неактивный — card.
    """

    OPTIONS = (("dpi", "DPI"), ("vpn", "VPN"))

    def __init__(
        self,
        master: tk.Misc,
        value: str = "dpi",
        on_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._selected = value if value in ("dpi", "vpn") else "dpi"
        self._on_change = on_change
        self._buttons: Dict[str, tk.Label] = {}

        row = tk.Frame(self, bg=THEME.card, padx=2, pady=2)
        row.pack()

        for mode_id, label_text in self.OPTIONS:
            btn = tk.Label(
                row, text=label_text,
                bg=THEME.card, fg=THEME.text_secondary,
                font=(THEME.font_ui, 9, "bold"),
                padx=12, pady=3, cursor="hand2",
            )
            btn.pack(side="left", padx=1)
            btn.bind("<Enter>", lambda _e, b=btn, m=mode_id: self._hover(b, m))
            btn.bind("<Leave>", lambda _e, b=btn: self._leave(b))
            btn.bind("<Button-1>", lambda _e, m=mode_id: self._on_pick(m))
            self._buttons[mode_id] = btn
        self._refresh()

    def get(self) -> str:
        return self._selected

    def _on_pick(self, mode: str) -> None:
        if mode == self._selected:
            return
        self._selected = mode
        self._refresh()
        if self._on_change:
            try:
                self._on_change(mode)
            except Exception:
                pass

    def _hover(self, btn: tk.Label, mode: str) -> None:
        if mode != self._selected:
            btn.configure(bg=THEME.card_hover, fg=THEME.text_primary)

    def _leave(self, btn: tk.Label) -> None:
        mode = [m for m, b in self._buttons.items() if b is btn][0]
        if mode != self._selected:
            btn.configure(bg=THEME.card, fg=THEME.text_secondary)

    def _refresh(self) -> None:
        for mode_id, btn in self._buttons.items():
            if mode_id == self._selected:
                btn.configure(bg=THEME.accent, fg=THEME.bg)
            else:
                btn.configure(bg=THEME.card, fg=THEME.text_secondary)


_FLAG_W = 22
_FLAG_H = 14


def _stripes_h(canvas: tk.Canvas, colors: tuple[str, ...]) -> None:
    n = len(colors)
    for i, c in enumerate(colors):
        canvas.create_rectangle(0, i * _FLAG_H / n, _FLAG_W, (i + 1) * _FLAG_H / n, fill=c, outline="")


def _stripes_v(canvas: tk.Canvas, colors: tuple[str, ...]) -> None:
    n = len(colors)
    for i, c in enumerate(colors):
        canvas.create_rectangle(i * _FLAG_W / n, 0, (i + 1) * _FLAG_W / n, _FLAG_H, fill=c, outline="")


def _draw_flag(canvas: tk.Canvas, code: str) -> None:
    """Нарисовать упрощённый флаг страны на маленьком Canvas по ISO-коду.

    Windows Tk не умеет рисовать flag-эмодзи как иконки (показывает как текст
    из двух букв) — поэтому рисуем сами. Вся таблица флагов и их отрисовка
    живёт в ``app.countries`` (единый источник и для определения кода страны
    по тегу сервера в ``singbox_config``), здесь только прокидываем размеры
    и цвета темы для неизвестных кодов.
    """
    countries.draw_flag(
        canvas, code, _FLAG_W, _FLAG_H,
        fallback_bg=THEME.card_hover, fallback_fg=THEME.text_secondary,
    )


class ServerListBox(tk.Frame):
    """Список серверов подписки: флаг страны + тег + пинг, как в Happ/v2rayTun.

    Каждая строка кликабельна (выбор локации), сверху — заголовок со счётом
    найденных серверов и две кнопки: «обновить подписку» и «замерить пинг».
    Сам виджет не делает сеть/сокеты — только рисует то, что ему передают
    через ``set_servers``/``set_ping``; вся работа (фетч подписки, TCP-пинг)
    остаётся на стороне вызывающего кода (см. ``ui_app.py``), чтобы не
    блокировать Tk-петлю и не тащить бизнес-логику в виджет.
    """

    def __init__(
        self,
        master: tk.Misc,
        on_select: Optional[Callable[[str], None]] = None,
        on_refresh: Optional[Callable[[], None]] = None,
        on_ping: Optional[Callable[[], None]] = None,
        height: int = 220,
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._on_select = on_select
        self._on_refresh = on_refresh
        self._on_ping = on_ping
        self._servers: list[dict] = []
        self._selected_tag: str = ""
        self._rows: Dict[str, Dict[str, tk.Widget]] = {}
        self._pings: Dict[str, int] = {}

        head = tk.Frame(self, bg=THEME.bg)
        head.pack(fill="x")
        self._count_lbl = tk.Label(
            head, text="серверы: —",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"), anchor="w",
        )
        self._count_lbl.pack(side="left")

        self._sort_btn = tk.Label(
            head, text="  сортировка  ",
            fg=THEME.text_secondary, bg=THEME.card,
            font=(THEME.font_ui, 8, "bold"), cursor="hand2",
            padx=6, pady=2,
        )
        self._sort_btn.pack(side="right", padx=(6, 0))
        self._sort_btn.bind("<Button-1>", lambda _e: self._click_sort())

        self._ping_btn = tk.Label(
            head, text="  пинг  ",
            fg=THEME.text_secondary, bg=THEME.card,
            font=(THEME.font_ui, 8, "bold"), cursor="hand2",
            padx=6, pady=2,
        )
        self._ping_btn.pack(side="right", padx=(6, 0))
        self._ping_btn.bind("<Button-1>", lambda _e: self._click_ping())

        self._refresh_btn = tk.Label(
            head, text="  обновить  ",
            fg=THEME.text_secondary, bg=THEME.card,
            font=(THEME.font_ui, 8, "bold"), cursor="hand2",
            padx=6, pady=2,
        )
        self._refresh_btn.pack(side="right", padx=(6, 0))
        self._refresh_btn.bind("<Button-1>", lambda _e: self._click_refresh())

        outer = tk.Frame(self, bg=THEME.border, bd=0)
        outer.pack(fill="both", expand=True, pady=(6, 0))
        canvas = tk.Canvas(
            outer, bg=THEME.bg, highlightthickness=0, bd=0, height=height,
        )
        canvas.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)

        body = tk.Frame(canvas, bg=THEME.bg)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(body_id, width=e.width))

        def _on_wheel(e: tk.Event) -> str:
            try:
                delta = int(-1 * (e.delta / 120))
            except Exception:
                delta = -1 if getattr(e, "num", 0) == 4 else 1
            canvas.yview_scroll(delta, "units")
            return "break"

        for w in (canvas, body):
            w.bind("<MouseWheel>", _on_wheel, add="+")
            w.bind("<Button-4>", _on_wheel, add="+")
            w.bind("<Button-5>", _on_wheel, add="+")

        self._canvas = canvas
        self._body = body
        self._wheel = _on_wheel

    # ── публичный API ────────────────────────────────────────────────────
    def set_servers(self, servers: list[dict], selected_tag: str = "") -> None:
        """Перерисовать список. ``servers`` — как из ``singbox_config.list_servers``."""
        self._servers = list(servers)
        self._selected_tag = selected_tag or (servers[0]["tag"] if servers else "")
        # ``_body`` пересобирается с нуля при каждом вызове — включая
        # empty-label, которую нельзя переиспользовать как атрибут, иначе
        # после первого destroy() она будет ссылаться на мёртвый виджет.
        for child in self._body.winfo_children():
            child.destroy()
        self._rows = {}
        self._pings = {}

        if not servers:
            tk.Label(
                self._body, text="ссылка не задана",
                fg=THEME.text_muted, bg=THEME.bg,
                font=(THEME.font_ui, 9), pady=14,
            ).pack(fill="x")
            self._count_lbl.configure(text="серверы: —")
            return

        self._count_lbl.configure(text=f"серверы: найдено {len(servers)}")
        for srv in servers:
            self._add_row(srv)
        self._highlight_selected()

    def set_selected(self, tag: str) -> None:
        self._selected_tag = tag
        self._highlight_selected()

    def set_ping(self, tag: str, ms: int) -> None:
        """Обновить текст пинга одной строки (``-1`` → «недоступен»)."""
        self._pings[tag] = ms
        row = self._rows.get(tag)
        if not row:
            return
        lbl = row["ping"]
        if ms < 0:
            lbl.configure(text="—", fg=THEME.danger_dim)
        elif ms < 150:
            lbl.configure(text=f"{ms} мс", fg=THEME.accent)
        elif ms < 400:
            lbl.configure(text=f"{ms} мс", fg=THEME.text_secondary)
        else:
            lbl.configure(text=f"{ms} мс", fg=THEME.danger_dim)

    def set_pinging(self, pinging: bool) -> None:
        self._ping_btn.configure(
            text="  замер…  " if pinging else "  пинг  ",
            fg=THEME.text_muted if pinging else THEME.text_secondary,
        )

    def set_refreshing(self, refreshing: bool) -> None:
        self._refresh_btn.configure(
            text="  обновляю…  " if refreshing else "  обновить  ",
            fg=THEME.text_muted if refreshing else THEME.text_secondary,
        )

    # ── internal ─────────────────────────────────────────────────────────
    def _add_row(self, srv: dict) -> None:
        from .singbox_config import guess_country_code, clean_tag

        tag = srv["tag"]
        clean_name = clean_tag(tag)
        country_code = guess_country_code(tag)

        row = tk.Frame(self._body, bg=THEME.bg, cursor="hand2")
        row.pack(fill="x")
        inner = tk.Frame(row, bg=THEME.bg, padx=8, pady=6)
        inner.pack(fill="x")

        flag = tk.Canvas(
            inner, width=_FLAG_W, height=_FLAG_H,
            bg=THEME.bg, highlightthickness=0, bd=0,
        )
        if country_code:
            _draw_flag(flag, country_code)
            flag.pack(side="left", padx=(0, 6))
        else:
            flag = None

        name = tk.Label(
            inner, text=clean_name,
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 10), anchor="w",
        )
        name.pack(side="left", fill="x", expand=True)

        ping = tk.Label(
            inner, text="—",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9, "bold"), anchor="e",
        )
        ping.pack(side="right")

        widgets = tuple(w for w in (row, inner, flag, name, ping) if w is not None)
        for w in widgets:
            w.bind("<Button-1>", lambda _e, t=tag: self._click_row(t))
            w.bind("<MouseWheel>", self._wheel, add="+")
            w.bind("<Button-4>", self._wheel, add="+")
            w.bind("<Button-5>", self._wheel, add="+")
        self._rows[tag] = {"row": row, "name": name, "ping": ping}

    def _highlight_selected(self) -> None:
        for tag, row in self._rows.items():
            selected = tag == self._selected_tag
            bg = THEME.card_hover if selected else THEME.bg
            fg = THEME.accent if selected else THEME.text_primary
            row["row"].configure(bg=bg)
            for key in ("name",):
                row[key].configure(bg=bg, fg=fg)
            row["ping"].configure(bg=bg)
            for child in row["row"].winfo_children():
                child.configure(bg=bg)

    def _click_row(self, tag: str) -> None:
        self._selected_tag = tag
        self._highlight_selected()
        if self._on_select:
            try:
                self._on_select(tag)
            except Exception:
                log.exception("ServerListBox on_select failed")

    def _click_refresh(self) -> None:
        if self._on_refresh:
            try:
                self._on_refresh()
            except Exception:
                log.exception("ServerListBox on_refresh failed")

    def _click_ping(self) -> None:
        if self._on_ping:
            try:
                self._on_ping()
            except Exception:
                log.exception("ServerListBox on_ping failed")

    def _click_sort(self) -> None:
        """Пересортировать список по возрастанию пинга (недоступные — вниз).

        Замеры берём из последнего «пинга»; если пинг ещё не замеряли —
        кнопка просто ничего не меняет (все tag’и без замера равны).
        """
        if not self._servers:
            return

        def _key(srv):
            ms = self._pings.get(srv["tag"], None)
            if ms is None or ms < 0:
                return (1, 10 ** 9)
            return (0, ms)

        self._servers.sort(key=_key)
        # перерисовать в новом порядке, сохранив уже показанные замеры
        saved = dict(self._pings)
        for child in self._body.winfo_children():
            child.destroy()
        self._rows = {}
        for srv in self._servers:
            self._add_row(srv)
        self._highlight_selected()
        self._pings = saved
        for tag, ms in list(saved.items()):
            if tag in self._rows:
                self.set_ping(tag, ms)


class AdBanner(tk.Frame):
    """Рекламный блок для VPN-режима: картинка-баннер + подпись под ней.

    Картинка ``resources/banner.jpg`` грузится через Pillow, масштабируется
    под заданную ширину (по высоте — пропорционально) и показывается как
    кликабельный ``tk.Label``. Под ней — привлекающая внимание подпись в
    стиле ``THEME``. Клик по картинке открывает реферальную ссылку в
    браузере по умолчанию (``webbrowser.open``).

    Если PIL недоступен или картинка не найдена — блок показывается в
    «текстовом» fallback-режиме (кликабельная плашка без изображения),
    чтобы VPN-экран не падал целиком.
    """

    # Реферальная ссылка Telegram-бота (см. задачу 3 ТЗ).
    BANNER_URL = "https://t.me/darknetvpnbot?start=ref11KbZfpA"

    def __init__(
        self,
        master: tk.Misc,
        width: int = 320,
        url: Optional[str] = None,
        on_click: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(
            master,
            bg=THEME.bg,
            highlightbackground=THEME.border,
            highlightthickness=0,
            bd=0,
        )
        self._width = max(160, int(width))
        self._url = url or self.BANNER_URL
        self._on_click = on_click
        # PhotoImage нужно держать ссылкой, иначе Tk его соберёт GC.
        self._photo: Optional[object] = None

        self._build()

    # ── построение UI ────────────────────────────────────────────────────
    def _build(self) -> None:
        # кликабельный «холст»-обёртка под картинку: если картинка есть —
        # показываем её; если нет — fallback-плашку с текстом.
        self._img_label = tk.Label(self, bg=THEME.bg, bd=0, cursor="hand2")
        self._img_label.pack(fill="x", padx=8, pady=(8, 4))
        self._img_label.bind("<Button-1>", lambda _e: self._open_url())

        # подпись под баннером — короткая, яркая, по центру.
        self._caption = tk.Label(
            self,
            text=(
                "Попробуйте 7 дней бесплатно\n\n"
                "Надежный обход блокировок на максимальной скорости."
            ),
            bg=THEME.bg,
            fg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"),
            justify="center",
            cursor="hand2",
            pady=4,
        )
        self._caption.pack(fill="x", padx=8, pady=(0, 8))
        self._caption.bind("<Button-1>", lambda _e: self._open_url())

        self._load_image()

    def _load_image(self) -> None:
        """Загрузить banner.jpg через Pillow и вписать в ``self._width``.

        При любой ошибке показываем текстовую заглушку, чтобы блок
        оставался кликабельным.
        """
        try:
            from PIL import Image, ImageTk
        except Exception:
            log.warning("PIL недоступен — AdBanner в fallback-режиме")
            self._show_fallback()
            return

        try:
            from . import paths
            img_path = paths.banner_image()
            if not img_path.exists():
                log.warning("banner.jpg не найден: %s", img_path)
                self._show_fallback()
                return

            img = Image.open(str(img_path))
            img.load()
        except Exception:
            log.exception("AdBanner: не удалось открыть banner.jpg")
            self._show_fallback()
            return

        # масштабируем по ширине, сохраняя пропорции
        w, h = img.size
        if w <= 0 or h <= 0:
            self._show_fallback()
            return
        new_w = self._width
        new_h = max(1, int(h * (new_w / w)))
        try:
            resample = Image.Resampling.LANCZOS  # Pillow >= 9.1
        except AttributeError:  # pragma: no cover
            resample = Image.LANCZOS  # type: ignore[attr-defined]
        try:
            img = img.resize((new_w, new_h), resample)
        except Exception:
            log.exception("AdBanner: resize failed")
            self._show_fallback()
            return

        try:
            self._photo = ImageTk.PhotoImage(img)
        except Exception:
            log.exception("AdBanner: PhotoImage failed")
            self._show_fallback()
            return

        self._img_label.configure(image=self._photo, text="")

    def _show_fallback(self) -> None:
        """Текстовая плашка вместо картинки (кликабельная)."""
        self._photo = None
        self._img_label.configure(
            image="",
            text="🚀  ЗАБРАТЬ VPN",
            compound="top",
            fg=THEME.bg,
            bg=THEME.accent,
            font=(THEME.font_ui, 13, "bold"),
            width=self._width,
            height=80,
        )

    # ── public ──────────────────────────────────────────────────────────
    def set_caption(self, text: str) -> None:
        """Сменить текст подписи под баннером."""
        self._caption.configure(text=text)

    def set_url(self, url: str) -> None:
        """Сменить URL, открываемый по клику."""
        self._url = url

    def reload_image(self) -> None:
        """Перечитать banner.jpg (например, после смены темы/ресурсов)."""
        self._load_image()

    # ── internal ─────────────────────────────────────────────────────────
    def _open_url(self) -> None:
        """Открыть реферальную ссылку в браузере по умолчанию.

        Сначала дёргаем пользовательский ``on_click`` (если задан), потом
        сам ``webbrowser.open`` — он не блокирует и не падает на отсутствии
        ассоциаций (просто возвращает False).
        """
        if self._on_click:
            try:
                self._on_click()
            except Exception:
                pass
        try:
            import webbrowser
            webbrowser.open(self._url, new=2)
        except Exception:
            log.exception("AdBanner: webbrowser.open failed")


# В widgets не должно быть логов на уровне модуля, но AdBanner использует
# log.warning — подключаем lazily-совместимый модульный логгер.
import logging  # noqa: E402
log = logging.getLogger("dpibypass.widgets")
