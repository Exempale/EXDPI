"""Кастомные виджеты: гладкий тоггл, иконки, бейдж статуса."""
from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, Optional

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
        """Иконка-«полумесяц/солнце» — переключение темы.

        Полный круг закрашен текущим цветом, второй круг того же фона
        накладывается со сдвигом — получается полумесяц.
        """
        bg = str(self.cget("bg"))
        pad = s * 0.22
        self.create_oval(pad, pad, s - pad, s - pad, fill=color, outline="")
        # вырезаем «другой круг» цветом фона — получается полумесяц
        cut = s * 0.18
        self.create_oval(
            pad + cut * 0.4, pad - cut * 0.2,
            s - pad + cut * 0.6, s - pad - cut * 0.2,
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
