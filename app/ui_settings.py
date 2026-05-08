"""Окно настроек — единая тема."""
from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

from . import paths
from .theme import THEME
from .widgets import IconButton
from .zapret_runner import list_strategies


def _hex_to_rgb(c: str):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


class _Field(tk.Frame):
    """Подпись + одна строка ввода с подчёркиванием в стиле темы."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        value: str,
        *,
        readonly: bool = False,
        validate: Optional[Callable[[str], bool]] = None,
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._validate = validate

        self._label = tk.Label(
            self,
            text=label.upper(),
            fg=THEME.text_secondary,
            bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        )
        self._label.pack(fill="x")

        self._var = tk.StringVar(value=value)
        self._entry = tk.Entry(
            self,
            textvariable=self._var,
            bg=THEME.card,
            fg=THEME.text_primary,
            insertbackground=THEME.accent,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME.border,
            highlightcolor=THEME.accent_dim,
            font=(THEME.font_ui, 10),
            disabledbackground=THEME.card,
            disabledforeground=THEME.text_muted,
        )
        if readonly:
            self._entry.configure(state="readonly", readonlybackground=THEME.card)
        self._entry.pack(fill="x", ipady=6, pady=(4, 0))

        self._var.trace_add("write", self._on_change)

    def get(self) -> str:
        return self._var.get().strip()

    def set(self, value: str) -> None:
        self._var.set(value)

    def _on_change(self, *_a) -> None:
        if self._validate is None:
            return
        ok = self._validate(self._var.get().strip())
        self._entry.configure(highlightbackground=THEME.border if ok else THEME.danger)


class _Select(tk.Frame):
    """Выпадающий список в стиле темы."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        options: List[str],
        value: str,
    ) -> None:
        super().__init__(master, bg=THEME.bg)

        tk.Label(
            self,
            text=label.upper(),
            fg=THEME.text_secondary,
            bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(fill="x")

        self._var = tk.StringVar(value=value if value in options else (options[0] if options else ""))

        style_name = f"DPI.{id(self)}.TCombobox"
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            style_name,
            fieldbackground=THEME.card,
            background=THEME.card,
            foreground=THEME.text_primary,
            arrowcolor=THEME.text_secondary,
            bordercolor=THEME.border,
            lightcolor=THEME.card,
            darkcolor=THEME.card,
            insertcolor=THEME.text_primary,
            selectbackground=THEME.accent_dark,
            selectforeground=THEME.text_primary,
            relief="flat",
            padding=(8, 4),
        )
        # важно: в состоянии readonly/active/focus ttk обычно подменяет
        # fieldbackground на белый; жёстко фиксируем на тёмный для всех состояний.
        style.map(
            style_name,
            fieldbackground=[
                ("readonly", THEME.card),
                ("focus", THEME.card),
                ("active", THEME.card),
                ("!disabled", THEME.card),
            ],
            foreground=[
                ("readonly", THEME.text_primary),
                ("focus", THEME.text_primary),
                ("active", THEME.text_primary),
            ],
            selectbackground=[("readonly", THEME.card), ("focus", THEME.card)],
            selectforeground=[("readonly", THEME.text_primary), ("focus", THEME.text_primary)],
            background=[("readonly", THEME.card), ("active", THEME.card)],
            arrowcolor=[("active", THEME.accent), ("!disabled", THEME.text_secondary)],
            bordercolor=[("focus", THEME.accent_dim), ("!disabled", THEME.border)],
            lightcolor=[("focus", THEME.card), ("!disabled", THEME.card)],
            darkcolor=[("focus", THEME.card), ("!disabled", THEME.card)],
        )

        # стилизация поповера выпадающего списка — ОБЯЗАТЕЛЬНО ДО создания Combobox,
        # иначе Tk не подхватывает их; кроме того вызываем на корне (winfo_toplevel),
        # иначе из вложенного Frame эффекта не будет.
        top = self.winfo_toplevel()
        top.option_add("*TCombobox*Listbox.background", THEME.card)
        top.option_add("*TCombobox*Listbox.foreground", THEME.text_primary)
        top.option_add("*TCombobox*Listbox.selectBackground", THEME.accent_dark)
        top.option_add("*TCombobox*Listbox.selectForeground", THEME.text_primary)
        top.option_add("*TCombobox*Listbox.borderWidth", 0)
        top.option_add("*TCombobox*Listbox.relief", "flat")
        top.option_add("*TCombobox*Listbox.font", f"{{{THEME.font_ui}}} 10")
        top.option_add("*TCombobox*Listbox.highlightThickness", 0)
        top.option_add("*TCombobox*Listbox.activeStyle", "none")

        self._cb = ttk.Combobox(
            self,
            textvariable=self._var,
            values=options,
            style=style_name,
            font=(THEME.font_ui, 10),
            state="readonly",
        )
        self._cb.pack(fill="x", ipady=6, pady=(4, 0))

        # снимаем яркое выделение выбранного текста в поле (это источник белого фона)
        self._cb.bind("<<ComboboxSelected>>", lambda _e: self._cb.selection_clear())
        self._cb.bind("<FocusIn>", lambda _e: self._cb.selection_clear())

    def get(self) -> str:
        return self._var.get()


class _CheckRow(tk.Frame):
    """Строка с описанием и переключателем-чекбоксом."""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        subtitle: str,
        value: bool,
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._var = tk.BooleanVar(value=value)
        self._on = value

        left = tk.Frame(self, bg=THEME.bg)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left, text=title, fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 10, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            left, text=subtitle, fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9), anchor="w", wraplength=260, justify="left",
        ).pack(fill="x", pady=(2, 0))

        # mini toggle
        self._cv = tk.Canvas(
            self, width=44, height=22, bg=THEME.bg,
            highlightthickness=0, bd=0,
        )
        self._cv.pack(side="right", padx=(8, 0))
        self._cv.bind("<Button-1>", self._toggle)
        self._cv.bind("<Enter>", lambda _e: self._cv.configure(cursor="hand2"))
        self._draw()

    def get(self) -> bool:
        return bool(self._var.get())

    def _toggle(self, _e: tk.Event) -> None:
        self._on = not self._on
        self._var.set(self._on)
        self._draw()

    def _draw(self) -> None:
        self._cv.delete("all")
        track = THEME.track_on if self._on else THEME.track_off
        knob = THEME.knob_on if self._on else THEME.knob_off
        # rounded track
        r = 11
        self._cv.create_oval(0, 0, 22, 22, fill=track, outline="")
        self._cv.create_oval(22, 0, 44, 22, fill=track, outline="")
        self._cv.create_rectangle(11, 0, 33, 22, fill=track, outline="")
        # knob
        x = 24 if self._on else 2
        self._cv.create_oval(x, 2, x + 18, 20, fill=knob, outline="")


class SettingsWindow(tk.Toplevel):
    """Скользящее окно настроек поверх основного."""

    WIDTH = 420
    HEIGHT = 720

    def __init__(self, master: tk.Tk, cfg: Dict[str, Any], on_save: Callable[[Dict[str, Any]], None]) -> None:
        super().__init__(master)
        self.cfg = dict(cfg)
        self.on_save = on_save

        self.title("EXDPI · настройки")
        self.configure(bg=THEME.bg)
        self.resizable(True, True)
        self.minsize(420, 700)
        self.transient(master)
        self.grab_set()

        try:
            ico = paths.icon_ico()
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

        self._build()

        # размер по контенту, центрируем относительно master
        self.update_idletasks()
        req_w = max(self.WIDTH, self.winfo_reqwidth())
        req_h = max(self.HEIGHT, self.winfo_reqheight())
        screen_h = self.winfo_screenheight()
        screen_w = self.winfo_screenwidth()
        # не выше экрана
        req_h = min(req_h, screen_h - 80)
        req_w = min(req_w, screen_w - 40)

        mx = master.winfo_rootx()
        my = master.winfo_rooty()
        mw = master.winfo_width()
        mh = master.winfo_height()
        x = mx + (mw - req_w) // 2
        y = my + (mh - req_h) // 2
        # держим в пределах экрана
        x = max(10, min(x, screen_w - req_w - 10))
        y = max(10, min(y, screen_h - req_h - 60))
        self.geometry(f"{req_w}x{req_h}+{x}+{y}")

    def _build(self) -> None:
        outer = tk.Frame(self, bg=THEME.bg, padx=22, pady=20)
        outer.pack(fill="both", expand=True)

        # header
        header = tk.Frame(outer, bg=THEME.bg)
        header.pack(fill="x")
        IconButton(
            header, glyph="back", size=24,
            on_click=self._cancel, tooltip="Назад",
        ).pack(side="left")
        title_box = tk.Frame(header, bg=THEME.bg)
        title_box.pack(side="left", padx=(12, 0))
        tk.Label(
            title_box, text="НАСТРОЙКИ",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box, text="EXDPI",
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 13, "bold"),
            anchor="w",
        ).pack(anchor="w")

        # Tabs / sections — у нас всё компактно, без вкладок
        body = tk.Frame(outer, bg=THEME.bg)
        body.pack(fill="both", expand=True, pady=(20, 0))

        # zapret strategy
        self._strategy = _Select(
            body, "Стратегия обхода (zapret)",
            list_strategies(),
            self.cfg.get("zapret_strategy", "general (ALT10).bat"),
        )
        self._strategy.pack(fill="x", pady=(0, 14))

        # proxy port
        self._port = _Field(
            body, "Порт прокси",
            str(self.cfg.get("proxy_port", 1443)),
            validate=lambda v: v.isdigit() and 1 <= int(v) <= 65535,
        )
        self._port.pack(fill="x", pady=(0, 14))

        # proxy host
        self._host = _Field(
            body, "Хост (только локально)",
            str(self.cfg.get("proxy_host", "127.0.0.1")),
            validate=lambda v: bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", v)),
        )
        self._host.pack(fill="x", pady=(0, 14))

        # secret (read-only display, regen button)
        secret_row = tk.Frame(body, bg=THEME.bg)
        secret_row.pack(fill="x", pady=(0, 14))
        self._secret = _Field(
            secret_row, "Секрет (32 hex)",
            str(self.cfg.get("proxy_secret", "")),
            readonly=True,
        )
        self._secret.pack(fill="x")
        regen = tk.Label(
            secret_row, text="сгенерировать новый",
            fg=THEME.accent_dim, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"),
            cursor="hand2",
        )
        regen.pack(anchor="e", pady=(4, 0))
        regen.bind("<Button-1>", lambda _e: self._regen_secret())

        # toggles
        self._zapret_on = _CheckRow(
            body, "DPI bypass (zapret)",
            "Запускать winws.exe в фоне для обхода DPI Discord/YouTube/etc.",
            bool(self.cfg.get("zapret_enabled", True)),
        )
        self._zapret_on.pack(fill="x", pady=(4, 8))

        self._proxy_on = _CheckRow(
            body, "Telegram MTProto Proxy",
            "Локальный прокси, чтобы Telegram Desktop ходил через WebSocket.",
            bool(self.cfg.get("proxy_enabled", True)),
        )
        self._proxy_on.pack(fill="x", pady=(0, 8))

        # footer (жёстко приколочен к низу окна)
        footer = tk.Frame(outer, bg=THEME.bg)
        footer.pack(side="bottom", fill="x", pady=(10, 0))

        # кнопки — в самый низ, чтобы их было видно всегда
        buttons = tk.Frame(footer, bg=THEME.bg)
        buttons.pack(side="bottom", fill="x", pady=(8, 0))

        # кредит над кнопками
        credit = tk.Frame(footer, bg=THEME.bg)
        credit.pack(side="bottom", fill="x")
        tk.Label(
            credit, text="автор · Exempale",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9, "bold"),
        ).pack(anchor="center")
        tk.Label(
            credit,
            text="сборка поверх zapret-discord-youtube и tg-ws-proxy",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 8),
        ).pack(anchor="center", pady=(2, 0))
        tk.Label(
            credit,
            text="ориг. авторы: Flowseal / bol-van · tg-ws-proxy",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 8),
        ).pack(anchor="center", pady=(0, 0))

        cancel = tk.Label(
            buttons, text="отмена",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 10), cursor="hand2",
        )
        cancel.pack(side="left", padx=(2, 0))
        cancel.bind("<Button-1>", lambda _e: self._cancel())

        save = tk.Label(
            buttons, text="  сохранить  ",
            fg=THEME.bg, bg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"),
            cursor="hand2", padx=18, pady=8,
        )
        save.pack(side="right")
        save.bind("<Button-1>", lambda _e: self._save())
        save.bind("<Enter>", lambda _e: save.configure(bg=THEME.accent_dim))
        save.bind("<Leave>", lambda _e: save.configure(bg=THEME.accent))

    # actions
    def _regen_secret(self) -> None:
        self._secret.set(os.urandom(16).hex())

    def _save(self) -> None:
        port_s = self._port.get()
        if not port_s.isdigit() or not (1 <= int(port_s) <= 65535):
            self._shake(self._port)
            return
        host = self._host.get()
        if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
            self._shake(self._host)
            return

        out = dict(self.cfg)
        out["zapret_strategy"] = self._strategy.get()
        out["proxy_port"] = int(port_s)
        out["proxy_host"] = host
        out["proxy_secret"] = self._secret.get() or os.urandom(16).hex()
        out["zapret_enabled"] = self._zapret_on.get()
        out["proxy_enabled"] = self._proxy_on.get()

        self.on_save(out)
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()

    def _shake(self, w: tk.Widget) -> None:
        x = w.winfo_x()
        for i, dx in enumerate([6, -6, 4, -4, 2, -2, 0]):
            self.after(40 * i, lambda d=dx: w.place_configure(x=x + d) if hasattr(w, "place_info") else None)
