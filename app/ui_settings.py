"""Окно настроек — единая тема."""
from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from . import easter, logs, presets, paths, securedns, settings_io
from .config import DEFAULT_CUSTOM_DOMAINS, GAME_MODES, normalize_domain_list, parse_domains
from .strategy_auto import AUTO_STRATEGY_ID, AUTO_STRATEGY_LABEL, is_auto
from .theme import THEME, available_themes, label_for as theme_label_for
from .widgets import IconButton
from .zapret_runner import list_strategies, open_service_bat


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

    def set(self, value: str) -> None:
        self._var.set(value)


class _DomainsBox(tk.Frame):
    """Поле для пользовательских доменов: мультистрока + загрузка из .txt."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        sub: str,
        value: List[str],
    ) -> None:
        super().__init__(master, bg=THEME.bg)

        tk.Label(
            self, text=label.upper(),
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            self, text=sub,
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9),
            anchor="w", wraplength=370, justify="left",
        ).pack(fill="x", pady=(2, 4))

        self._txt = tk.Text(
            self, height=5,
            bg=THEME.card, fg=THEME.text_primary,
            insertbackground=THEME.accent,
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground=THEME.border,
            highlightcolor=THEME.accent_dim,
            font=(THEME.font_ui, 10),
            wrap="word", padx=8, pady=6,
            selectbackground=THEME.accent_dark,
            selectforeground=THEME.text_primary,
        )
        self._txt.pack(fill="x")
        if value:
            self._txt.insert("1.0", "; ".join(value))
        self._txt.bind("<KeyRelease>", lambda _e: self._update_count())

        # row: counter + actions
        row = tk.Frame(self, bg=THEME.bg)
        row.pack(fill="x", pady=(4, 0))

        self._count_lbl = tk.Label(
            row, text="",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9),
        )
        self._count_lbl.pack(side="left")

        load = tk.Label(
            row, text="загрузить .txt",
            fg=THEME.accent_dim, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"),
            cursor="hand2",
        )
        load.pack(side="right")
        load.bind("<Button-1>", lambda _e: self._load_file())

        defaults = tk.Label(
            row, text="дефолты",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"),
            cursor="hand2",
        )
        defaults.pack(side="right", padx=(0, 12))
        defaults.bind("<Button-1>", lambda _e: self._reset_defaults())

        clear = tk.Label(
            row, text="очистить",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"),
            cursor="hand2",
        )
        clear.pack(side="right", padx=(0, 12))
        clear.bind("<Button-1>", lambda _e: self._clear())

        self._update_count()

    def get(self) -> List[str]:
        return parse_domains(self._txt.get("1.0", "end"))

    def _set_text(self, items: List[str]) -> None:
        self._txt.delete("1.0", "end")
        if items:
            self._txt.insert("1.0", "; ".join(items))
        self._update_count()

    def _clear(self) -> None:
        self._set_text([])

    def _reset_defaults(self) -> None:
        self._set_text(list(DEFAULT_CUSTOM_DOMAINS))

    def _update_count(self) -> None:
        n = len(self.get())
        if n == 0:
            txt = "пусто — будет создан плейсхолдер"
        elif n == 1:
            txt = "1 домен"
        elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
            txt = f"{n} домена"
        else:
            txt = f"{n} доменов"
        self._count_lbl.configure(text=txt)

    def _load_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выбрать .txt со списком доменов",
            filetypes=[("Текстовый файл", "*.txt"), ("Все файлы", "*.*")],
            parent=self.winfo_toplevel(),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fp:
                content = fp.read()
        except Exception as exc:
            messagebox.showerror(
                "EXDPI", f"Не удалось прочитать файл:\n{exc}",
                parent=self.winfo_toplevel(),
            )
            return
        existing = parse_domains(self._txt.get("1.0", "end"))
        loaded = parse_domains(content)
        seen = set(existing)
        merged = list(existing)
        for d in loaded:
            if d not in seen:
                seen.add(d)
                merged.append(d)
        self._set_text(merged)


class _PresetPicker(tk.Frame):
    """Ряд «кнопок-чипсов» для быстрого переключения готовых наборов доменов.

    При клике подгружает домены пресета в связанный ``_DomainsBox``. Текущий
    выбор подсвечивается акцентным цветом. Сохраняется как ``domain_preset``
    в config.json.
    """

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        sub: str,
        value: str,
        domains_box: "_DomainsBox",
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._domains_box = domains_box
        self._presets = presets.presets()
        self._selected = value if any(p.id == value for p in self._presets) else "custom"
        # сохранённый пользовательский список (для custom-вкладки) — отдельный
        # от пресетов, чтобы переключение туда-сюда не теряло его и не
        # подставляло домены прошлого пресета.
        if self._selected == "custom":
            self._custom_saved: List[str] = list(domains_box.get())
        else:
            self._custom_saved = []

        tk.Label(
            self, text=label.upper(),
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            self, text=sub,
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9),
            anchor="w", wraplength=370, justify="left",
        ).pack(fill="x", pady=(2, 6))

        self._chip_row = tk.Frame(self, bg=THEME.bg)
        self._chip_row.pack(fill="x")

        self._chips: Dict[str, tk.Label] = {}
        # описание текущего пресета — обновляется при выборе
        self._desc_lbl = tk.Label(
            self, text="",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9, "italic"),
            anchor="w", wraplength=370, justify="left",
        )
        self._desc_lbl.pack(fill="x", pady=(6, 0))

        for p in self._presets:
            chip = tk.Label(
                self._chip_row, text=" " + p.label + " ",
                bg=THEME.card, fg=THEME.text_secondary,
                font=(THEME.font_ui, 9),
                padx=10, pady=4, cursor="hand2",
            )
            chip.pack(side="left", padx=(0, 6), pady=(0, 4))
            chip.bind("<Button-1>", lambda _e, pid=p.id: self._on_pick(pid))
            self._chips[p.id] = chip

        self._refresh_chip_colors()
        self._refresh_desc()

    def get(self) -> str:
        return self._selected

    def _on_pick(self, preset_id: str) -> None:
        if preset_id == self._selected:
            return
        # уходим с custom — запомнить текущий пользовательский список
        if self._selected == "custom":
            self._custom_saved = list(self._domains_box.get())
        self._selected = preset_id
        self._refresh_chip_colors()
        self._refresh_desc()
        if preset_id == "custom":
            # вернулись к своему набору — восстановить ранее введённый список
            # (а не оставлять домены прошлого пресета).
            self._domains_box._set_text(list(self._custom_saved))
            return
        try:
            domains = presets.load_domains(preset_id)
        except Exception:
            domains = []
        if not domains:
            try:
                messagebox.showwarning(
                    "EXDPI",
                    "Пресет пуст или файл со списком доменов не найден.",
                    parent=self.winfo_toplevel(),
                )
            except Exception:
                pass
            return
        # подставить домены пресета (пользовательский список остался в _custom_saved)
        self._domains_box._set_text(domains)

    def _refresh_chip_colors(self) -> None:
        for pid, chip in self._chips.items():
            if pid == self._selected:
                chip.configure(bg=THEME.accent_dark, fg=THEME.text_primary)
            else:
                chip.configure(bg=THEME.card, fg=THEME.text_secondary)

    def _refresh_desc(self) -> None:
        p = presets.by_id(self._selected)
        if p:
            self._desc_lbl.configure(text=p.description)
        else:
            self._desc_lbl.configure(text="")


class _ModePicker(tk.Frame):
    """Сегментный переключатель «обычный / гейминг» для zapret.

    Сохраняется как ``game_mode`` в config.json. Влияет на подстановку
    %GameFilter*% при запуске winws.exe (см. zapret_runner.parse_strategy).
    """

    OPTIONS = (("normal", "обычный"), ("gaming", "гейминг"))

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        sub: str,
        value: str,
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._selected = value if value in GAME_MODES else "normal"

        tk.Label(
            self, text=label.upper(),
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            self, text=sub,
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9),
            anchor="w", wraplength=370, justify="left",
        ).pack(fill="x", pady=(2, 6))

        row = tk.Frame(self, bg=THEME.bg)
        row.pack(fill="x")

        self._buttons: Dict[str, tk.Label] = {}
        for mid, label_text in self.OPTIONS:
            btn = tk.Label(
                row, text=" " + label_text + " ",
                bg=THEME.card, fg=THEME.text_secondary,
                font=(THEME.font_ui, 10, "bold"),
                padx=14, pady=6, cursor="hand2",
            )
            btn.pack(side="left", padx=(0, 6))
            btn.bind("<Button-1>", lambda _e, m=mid: self._on_pick(m))
            self._buttons[mid] = btn
        self._refresh()

    def get(self) -> str:
        return self._selected

    def _on_pick(self, mode: str) -> None:
        if mode not in GAME_MODES:
            return
        self._selected = mode
        self._refresh()

    def _refresh(self) -> None:
        for mid, btn in self._buttons.items():
            if mid == self._selected:
                btn.configure(bg=THEME.accent, fg=THEME.bg)
            else:
                btn.configure(bg=THEME.card, fg=THEME.text_secondary)


class _ThemePicker(tk.Frame):
    """Радио-переключатель темы оформления (dark/light/midnight)."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        sub: str,
        value: str,
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._themes = available_themes()
        self._selected = value if value in self._themes else "dark"

        tk.Label(
            self, text=label.upper(),
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            self, text=sub,
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 9),
            anchor="w", wraplength=370, justify="left",
        ).pack(fill="x", pady=(2, 6))

        row = tk.Frame(self, bg=THEME.bg)
        row.pack(fill="x")

        self._buttons: Dict[str, tk.Label] = {}
        for name in self._themes:
            btn = tk.Label(
                row, text=" " + theme_label_for(name) + " ",
                bg=THEME.card, fg=THEME.text_secondary,
                font=(THEME.font_ui, 10, "bold"),
                padx=14, pady=6, cursor="hand2",
            )
            btn.pack(side="left", padx=(0, 6), pady=(0, 4))
            btn.bind("<Button-1>", lambda _e, n=name: self._on_pick(n))
            self._buttons[name] = btn
        self._refresh()

    def get(self) -> str:
        return self._selected

    def _on_pick(self, name: str) -> None:
        if name not in self._themes:
            return
        self._selected = name
        self._refresh()

    def _refresh(self) -> None:
        for name, btn in self._buttons.items():
            if name == self._selected:
                btn.configure(bg=THEME.accent, fg=THEME.bg)
            else:
                btn.configure(bg=THEME.card, fg=THEME.text_secondary)


class _CheckRow(tk.Frame):
    """Строка с описанием и переключателем-чекбоксом."""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        subtitle: str,
        value: bool,
        on_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        super().__init__(master, bg=THEME.bg)
        self._var = tk.BooleanVar(value=value)
        self._on = value
        self._on_change = on_change

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
        if self._on_change is not None:
            try:
                self._on_change(self._on)
            except Exception:
                pass

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

    WIDTH = 800
    HEIGHT = 630

    def __init__(
        self,
        master: tk.Tk,
        cfg: Dict[str, Any],
        on_save: Callable[[Dict[str, Any]], None],
        controller=None,
        on_run_wizard: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self.cfg = dict(cfg)
        self.on_save = on_save
        self._controller = controller
        self._on_run_wizard = on_run_wizard
        # mousewheel binding tag, чтобы корректно отвязать на close
        self._wheel_bind: Optional[str] = None

        self.title("EXDPI · настройки")
        self.configure(bg=THEME.bg)
        self.resizable(True, True)
        self.minsize(640, 480)
        self.transient(master)
        self.grab_set()

        try:
            ico = paths.icon_ico()
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

        self._build()

        # размер окна — фиксированный «удобный», но не выше экрана.
        # Содержимое всё равно скроллится, кнопки сохранить/отмена и кредит
        # прибиты к низу — поэтому на любом разрешении они видны.
        self.update_idletasks()
        screen_h = self.winfo_screenheight()
        screen_w = self.winfo_screenwidth()
        req_w = min(self.WIDTH, screen_w - 40)
        req_h = min(self.HEIGHT, screen_h - 80)

        mx = master.winfo_rootx()
        my = master.winfo_rooty()
        mw = master.winfo_width()
        mh = master.winfo_height()
        x = mx + (mw - req_w) // 2
        y = my + (mh - req_h) // 2
        x = max(10, min(x, screen_w - req_w - 10))
        y = max(10, min(y, screen_h - req_h - 60))
        self.geometry(f"{req_w}x{req_h}+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=THEME.bg)
        outer.pack(fill="both", expand=True)

        # ── header (зафиксирован сверху) ────────────────────────────
        header = tk.Frame(outer, bg=THEME.bg, padx=22, pady=20)
        header.pack(side="top", fill="x")
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

        # ── footer (зафиксирован снизу: кнопки + кредит) ───────────
        footer = tk.Frame(outer, bg=THEME.bg, padx=22, pady=14)
        footer.pack(side="bottom", fill="x")
        # тонкая разделительная линия над футером
        tk.Frame(outer, bg=THEME.border, height=1).pack(side="bottom", fill="x")

        buttons = tk.Frame(footer, bg=THEME.bg)
        buttons.pack(side="bottom", fill="x", pady=(8, 0))
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
        ).pack(anchor="center")

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

        # ── скроллируемое тело (между header и footer) ─────────────
        mid = tk.Frame(outer, bg=THEME.bg)
        mid.pack(side="top", fill="both", expand=True)

        canvas = tk.Canvas(
            mid, bg=THEME.bg, highlightthickness=0, bd=0,
        )
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)

        body = tk.Frame(canvas, bg=THEME.bg, padx=22, pady=4)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(_e: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e: tk.Event) -> None:
            canvas.itemconfigure(body_id, width=e.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # колесо мыши: привязываем рекурсивно к окну и всем дочерним виджетам
        # — bind_all + Enter/Leave срывается, когда курсор уходит на дочерний
        # виджет и Tk шлёт <Leave> на родителя.
        def _on_wheel(e: tk.Event) -> str:
            try:
                delta = int(-1 * (e.delta / 120))
            except Exception:
                delta = -1 if getattr(e, "num", 0) == 4 else 1
            canvas.yview_scroll(delta, "units")
            return "break"

        def _bind_wheel_recursive(widget: tk.Misc) -> None:
            try:
                widget.bind("<MouseWheel>", _on_wheel, add="+")
                widget.bind("<Button-4>", _on_wheel, add="+")
                widget.bind("<Button-5>", _on_wheel, add="+")
            except Exception:
                pass
            for ch in widget.winfo_children():
                _bind_wheel_recursive(ch)

        self._bind_wheel_recursive = _bind_wheel_recursive
        self._bind_wheel_recursive(self)

        # zapret strategy (+ спец-пункт «Авто»)
        strategy_value = str(self.cfg.get("zapret_strategy", "general (ALT10).bat"))
        strategy_display = AUTO_STRATEGY_LABEL if is_auto(strategy_value) else strategy_value
        self._strategy = _Select(
            body, "Стратегия обхода (zapret)",
            [AUTO_STRATEGY_LABEL] + list_strategies(),
            strategy_display,
        )
        self._strategy.pack(fill="x", pady=(0, 2))
        auto_row = tk.Frame(body, bg=THEME.bg)
        auto_row.pack(fill="x", pady=(0, 14))
        self._auto_hint = tk.Label(
            auto_row,
            text=self._auto_result_hint(),
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 8), anchor="w",
        )
        self._auto_hint.pack(side="left")
        auto_link = tk.Label(
            auto_row, text="подобрать автоматически",
            fg=THEME.accent_dim, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"), cursor="hand2",
        )
        auto_link.pack(side="right")
        auto_link.bind("<Button-1>", lambda _e: self._open_autostrategy())

        # режим работы запрета (обычный вс игровой)
        self._game_mode = _ModePicker(
            body, "Режим запрета",
            "Обычный — фильтр только по стандартным TLS/HTTP/QUIC портам. "
            "Гейминг — GameFilter=1024-65535 для TCP+UDP: голос Discord, "
            "игровые лобби, P2P.",
            value=str(self.cfg.get("game_mode", "normal")),
        )
        self._game_mode.pack(fill="x", pady=(0, 14))

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

        # пресеты готовых доменов (config lists)
        self._domains = _DomainsBox(
            body,
            "Свои домены для обхода",
            "Hostname по одному на строке или через ; . Попадают в "
            "list-general-user.txt zapret. Изменения применяются при следующем "
            "включении EXDPI.",
            normalize_domain_list(self.cfg.get("custom_domains") or []),
        )

        self._preset = _PresetPicker(
            body,
            "Готовые конфиг-листы",
            "Подборки доменов одним кликом: ИИ, игры, соцсети, РФ-блоки. "
            "«Свой набор» — пользовательский список (сохраняется отдельно).",
            value=str(self.cfg.get("domain_preset", "custom")),
            domains_box=self._domains,
        )
        self._preset.pack(fill="x", pady=(0, 8))

        self._domains.pack(fill="x", pady=(0, 14))

        # toggles
        self._zapret_on = _CheckRow(
            body, "DPI bypass (zapret)",
            "Запускать winws.exe в фоне для обхода DPI.",
            bool(self.cfg.get("zapret_enabled", True)),
        )
        self._zapret_on.pack(fill="x", pady=(4, 8))

        self._proxy_on = _CheckRow(
            body, "Telegram MTProto Proxy",
            "Локальный прокси для Telegram Desktop через WebSocket.",
            bool(self.cfg.get("proxy_enabled", True)),
        )
        self._proxy_on.pack(fill="x", pady=(0, 8))

        # ── разделитель ─────────────────────────────────────────────
        tk.Frame(body, bg=THEME.border, height=1).pack(fill="x", pady=(8, 10))

        # автозапуск с Windows
        self._autostart = _CheckRow(
            body, "Запускать с Windows",
            "Автозапуск при входе в систему через Планировщик заданий — "
            "сразу с правами администратора, без запроса UAC.",
            bool(self.cfg.get("autostart_with_windows", False)),
        )
        self._autostart.pack(fill="x", pady=(0, 8))

        # сворачивать в трей по крестику
        self._tray = _CheckRow(
            body, "Сворачивать в трей",
            "По крестику окно прячется в трей вместо выхода.",
            bool(self.cfg.get("minimize_to_tray", True)),
        )
        self._tray.pack(fill="x", pady=(0, 8))

        # запускать свёрнутым
        self._start_min = _CheckRow(
            body, "Запускать свёрнутым",
            "При старте программа сразу уходит в трей.",
            bool(self.cfg.get("start_minimized", False)),
        )
        self._start_min.pack(fill="x", pady=(0, 8))

        # уведомления Windows
        self._notify = _CheckRow(
            body, "Уведомления Windows",
            "Тосты о включении/выключении обхода, ошибках и обновлениях.",
            bool(self.cfg.get("notifications_enabled", True)),
        )
        self._notify.pack(fill="x", pady=(0, 8))

        # ── разделитель: защищённый DNS ─────────────────────────────
        tk.Frame(body, bg=THEME.border, height=1).pack(fill="x", pady=(8, 10))

        self._securedns_on = _CheckRow(
            body, "Защищённый DNS (DoH/DoT)",
            "Локальный DNS на 127.0.0.1: запросы к провайдеру шифруются, "
            "DPI не видит и не подменяет их. Включается вместе с обходом.",
            bool(self.cfg.get("securedns_enabled", False)),
        )
        self._securedns_on.pack(fill="x", pady=(0, 8))

        self._dns_proto_labels = {
            "doh": "DoH — DNS-over-HTTPS (порт 443)",
            "dot": "DoT — DNS-over-TLS (порт 853)",
        }
        proto_value = str(self.cfg.get("securedns_protocol", "doh"))
        self._dns_proto = _Select(
            body, "Протокол защищённого DNS",
            list(self._dns_proto_labels.values()),
            self._dns_proto_labels.get(proto_value, self._dns_proto_labels["doh"]),
        )
        self._dns_proto.pack(fill="x", pady=(0, 10))

        self._dns_provider_labels = securedns.provider_labels()
        provider_value = str(self.cfg.get("securedns_provider", "cloudflare"))
        self._dns_provider = _Select(
            body, "DNS-провайдер",
            list(self._dns_provider_labels.values()),
            self._dns_provider_labels.get(provider_value,
                                          self._dns_provider_labels["cloudflare"]),
        )
        self._dns_provider.pack(fill="x", pady=(0, 10))

        self._dns_system = _CheckRow(
            body, "Назначать системным DNS",
            "При включении прописывает 127.0.0.1 на активные адаптеры "
            "(старые DNS сохраняются и восстанавливаются при выключении).",
            bool(self.cfg.get("securedns_set_system", True)),
        )
        self._dns_system.pack(fill="x", pady=(0, 8))

        # ── разделитель ─────────────────────────────────────────────
        tk.Frame(body, bg=THEME.border, height=1).pack(fill="x", pady=(8, 10))

        # тема интерфейса
        self._theme = _ThemePicker(
            body, "Тема интерфейса",
            "Цветовая схема приложения. Применяется сразу.",
            value=str(self.cfg.get("theme", "dark")),
        )
        self._theme.pack(fill="x", pady=(0, 8))

        # ── разделитель: режим разработчика ─────────────────────────
        tk.Frame(body, bg=THEME.border, height=1).pack(fill="x", pady=(8, 10))

        # переключатель «Для разработчиков»: показывает/прячет сервисный раздел
        self._dev_mode = _CheckRow(
            body, "Для разработчиков",
            "Сервисные инструменты: логи, импорт/экспорт настроек, мастер "
            "первого запуска и запуск service.bat.",
            bool(self.cfg.get("developer_mode", False)),
            on_change=self._on_dev_mode_toggle,
        )
        self._dev_mode.pack(fill="x", pady=(0, 8))

        # контейнер сервисного раздела — пакуется только когда dev-режим включён
        self._dev_box = tk.Frame(body, bg=THEME.bg)

        tk.Label(
            self._dev_box, text="ДЛЯ РАЗРАБОТЧИКОВ",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"), anchor="w",
        ).pack(fill="x", pady=(2, 6))

        def _service_link(text: str, handler: Callable[[], None]) -> None:
            lbl = tk.Label(
                self._dev_box, text=text,
                fg=THEME.accent_dim, bg=THEME.bg,
                font=(THEME.font_ui, 10, "underline"),
                cursor="hand2", anchor="w",
            )
            lbl.pack(fill="x", pady=(0, 6))
            lbl.bind("<Button-1>", lambda _e: handler())

        _service_link("открыть папку с логами", self._open_logs)
        _service_link("экспортировать настройки…", self._export_settings)
        _service_link("импортировать настройки…", self._import_settings)
        if self._on_run_wizard is not None:
            _service_link("мастер первого запуска", self._run_wizard)

        # кнопка запуска service.bat (диспетчер/меню оригинального zapret)
        run_bat = tk.Label(
            self._dev_box, text="  запустить service.bat  ",
            fg=THEME.bg, bg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"),
            cursor="hand2", padx=14, pady=7,
        )
        run_bat.pack(anchor="w", pady=(4, 2))
        run_bat.bind("<Button-1>", lambda _e: self._open_service_bat())
        run_bat.bind("<Enter>", lambda _e: run_bat.configure(bg=THEME.accent_dim))
        run_bat.bind("<Leave>", lambda _e: run_bat.configure(bg=THEME.accent))
        tk.Label(
            self._dev_box,
            text="Откроет консольное меню zapret (запросит права администратора).",
            fg=THEME.text_muted, bg=THEME.bg,
            font=(THEME.font_ui, 8), anchor="w", wraplength=420, justify="left",
        ).pack(fill="x", pady=(0, 2))

        if bool(self.cfg.get("developer_mode", False)):
            self._dev_box.pack(fill="x", pady=(2, 0))

        # небольшой отступ снизу скролла, чтобы последний пункт не липал
        # к разделителю над футером
        tk.Frame(body, bg=THEME.bg, height=8).pack(fill="x")

        # перепривязать колесо мыши к новым дочерним виджетам
        try:
            self._bind_wheel_recursive(self)
        except Exception:
            pass

    # actions
    def _regen_secret(self) -> None:
        self._secret.set(os.urandom(16).hex())

    def _auto_result_hint(self) -> str:
        res = str(self.cfg.get("zapret_strategy_auto_result", "") or "")
        if res:
            short = res[:-4] if res.endswith(".bat") else res
            return f"последний авто-подбор: {short}"
        return "«Авто» использует результат авто-подбора"

    def _collect(self) -> Optional[Dict[str, Any]]:
        """Собрать значения всех виджетов в dict (или None при ошибке)."""
        port_s = self._port.get()
        if not port_s.isdigit() or not (1 <= int(port_s) <= 65535):
            self._shake(self._port)
            return None
        host = self._host.get()
        if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
            self._shake(self._host)
            return None

        out = dict(self.cfg)
        strategy_sel = self._strategy.get()
        out["zapret_strategy"] = (
            AUTO_STRATEGY_ID if strategy_sel == AUTO_STRATEGY_LABEL else strategy_sel
        )
        out["proxy_port"] = int(port_s)
        out["proxy_host"] = host
        out["proxy_secret"] = self._secret.get() or os.urandom(16).hex()
        out["zapret_enabled"] = self._zapret_on.get()
        out["proxy_enabled"] = self._proxy_on.get()
        out["custom_domains"] = self._domains.get()
        out["domain_preset"] = self._preset.get()
        out["game_mode"] = self._game_mode.get()
        out["autostart_with_windows"] = self._autostart.get()
        out["minimize_to_tray"] = self._tray.get()
        out["start_minimized"] = self._start_min.get()
        out["theme"] = self._theme.get()
        out["notifications_enabled"] = self._notify.get()
        out["developer_mode"] = self._dev_mode.get()
        out["securedns_enabled"] = self._securedns_on.get()
        proto_rev = {v: k for k, v in self._dns_proto_labels.items()}
        out["securedns_protocol"] = proto_rev.get(self._dns_proto.get(), "doh")
        provider_rev = {v: k for k, v in self._dns_provider_labels.items()}
        out["securedns_provider"] = provider_rev.get(self._dns_provider.get(), "cloudflare")
        out["securedns_set_system"] = self._dns_system.get()
        return out

    def _save(self) -> None:
        out = self._collect()
        if out is None:
            return
        self.on_save(out)
        self.destroy()

    # ── для разработчиков ───────────────────────────────────────────
    def _on_dev_mode_toggle(self, on: bool) -> None:
        """Показать/спрятать сервисный раздел при переключении dev-режима."""
        try:
            if on:
                self._dev_box.pack(fill="x", pady=(2, 0))
                # перепривязать колесо мыши к новым видимым виджетам
                try:
                    self._bind_wheel_recursive(self._dev_box)
                except Exception:
                    pass
            else:
                self._dev_box.pack_forget()
        except Exception:
            pass

    def _open_service_bat(self) -> None:
        if not open_service_bat():
            messagebox.showerror(
                "EXDPI", "Не удалось запустить service.bat.", parent=self)

    # ── сервис ──────────────────────────────────────────────────────
    def _open_logs(self) -> None:
        if not logs.open_logs_folder():
            messagebox.showerror("EXDPI", "Не удалось открыть папку с логами.", parent=self)

    def _export_settings(self) -> None:
        out = self._collect()
        if out is None:
            messagebox.showerror(
                "EXDPI", "Исправьте подсвеченные поля перед экспортом.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Экспорт настроек EXDPI",
            initialfile=settings_io.default_export_filename(),
            defaultextension=".json",
            filetypes=[("Настройки EXDPI", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        if settings_io.export_settings(out, path):
            messagebox.showinfo("EXDPI", "Настройки экспортированы.", parent=self)
        else:
            messagebox.showerror("EXDPI", "Не удалось сохранить файл.", parent=self)

    def _import_settings(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Импорт настроек EXDPI",
            filetypes=[("Настройки EXDPI", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        result = settings_io.import_settings(path)
        if not result.ok:
            messagebox.showerror("EXDPI", f"Импорт не удался: {result.error}", parent=self)
            return
        self.cfg.update(result.applied)
        # пересобрать окно с новыми значениями
        for w in self.winfo_children():
            w.destroy()
        self._build()
        note = f"Загружено настроек: {result.applied_count}."
        if result.skipped:
            note += f" Пропущено (битые/незнакомые): {len(result.skipped)}."
        note += "\nНажмите «сохранить», чтобы применить."
        messagebox.showinfo("EXDPI", note, parent=self)

    def _run_wizard(self) -> None:
        cb = self._on_run_wizard
        self.destroy()
        if cb is not None:
            cb()

    def _open_autostrategy(self) -> None:
        if self._controller is None:
            messagebox.showinfo(
                "EXDPI", "Авто-подбор недоступен в этом окне.", parent=self)
            return
        from .ui_autostrategy import AutoStrategyDialog

        def _on_applied(strategy: str) -> None:
            self.cfg["zapret_strategy"] = AUTO_STRATEGY_ID
            self.cfg["zapret_strategy_auto_result"] = strategy
            try:
                self._strategy.set(AUTO_STRATEGY_LABEL)
                self._auto_hint.configure(text=self._auto_result_hint())
            except Exception:
                pass

        AutoStrategyDialog(self, self._controller, on_applied=_on_applied)

    def _cancel(self) -> None:
        self.destroy()

    def _shake(self, w: tk.Widget) -> None:
        x = w.winfo_x()
        for i, dx in enumerate([6, -6, 4, -4, 2, -2, 0]):
            self.after(40 * i, lambda d=dx: w.place_configure(x=x + d) if hasattr(w, "place_info") else None)
