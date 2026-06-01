"""Окно-инструкция: как подключить локальный MTProto-прокси в Telegram.

Открывается из главного окна по клику «подключить прокси в Telegram». Показывает
пошаговую инструкцию для Telegram Desktop, мобильных клиентов (iOS / Android)
и отдельно — как использовать прокси в голосовых чатах (Voice Chats).

Содержимое окна минимально привязано к данным конфига: подставляется реальный
host:port и tg:// ссылка с актуальным секретом, чтобы пользователь мог
скопировать её в один клик.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Optional

from . import paths
from .theme import THEME
from .widgets import IconButton

log = logging.getLogger("dpibypass.ui.tg_guide")


_STEPS_DESKTOP = [
    ("1. Откройте настройки Telegram Desktop",
     "«Настройки» → «Продвинутые настройки» → «Тип соединения»."),
    ("2. Добавьте MTPROTO-прокси",
     "«Использовать пользовательский прокси» → «Добавить прокси» → тип «MTPROTO»."),
    ("3. Введите параметры из блока выше",
     "Сервер: 127.0.0.1. Порт и секрет — как указано выше."),
    ("4. Быстрее: вставьте готовую tg://-ссылку",
     "Скопируйте ссылку кнопкой ниже и вставьте в Telegram — поля заполнятся сами."),
    ("5. Включите EXDPI",
     "Нажмите большой переключатель ON. В Telegram появится значок активного прокси."),
]

_STEPS_VOICE = [
    ("Голосовые чаты и звонки",
     "Голос идёт через тот же MTPROTO-прокси — отдельной настройки не требуется. "
     "Если слышимость хромает, в настройках EXDPI попробуйте другую стратегию zapret "
     "(general ALT10 / FAKE TLS AUTO / SIMPLE FAKE) или включите режим «гейминг»."),
]


class TgVcGuideDialog(tk.Toplevel):
    WIDTH = 540
    HEIGHT = 620

    def __init__(self, master: tk.Tk, cfg: Dict[str, Any]) -> None:
        super().__init__(master)
        self.cfg = cfg
        self._wheel_bind: Optional[str] = None

        self.title("EXDPI · Telegram прокси")
        self.configure(bg=THEME.bg)
        self.resizable(True, True)
        self.minsize(440, 460)
        self.transient(master)
        self.grab_set()

        try:
            ico = paths.icon_ico()
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

        self._build()

        self.update_idletasks()
        sh = self.winfo_screenheight()
        sw = self.winfo_screenwidth()
        # реальная высота, нужная содержимому: header + footer + body.reqheight
        try:
            content_h = self.winfo_reqheight()
        except Exception:
            content_h = self.HEIGHT
        req_h = min(max(self.HEIGHT, content_h + 20), sh - 100)
        mx = master.winfo_rootx()
        my = master.winfo_rooty()
        mw = master.winfo_width()
        mh = master.winfo_height()
        x = mx + (mw - self.WIDTH) // 2
        y = my + (mh - req_h) // 2
        x = max(10, min(x, sw - self.WIDTH - 10))
        y = max(10, min(y, sh - req_h - 60))
        self.geometry(f"{self.WIDTH}x{req_h}+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=THEME.bg)
        outer.pack(fill="both", expand=True)

        # ── header ───────────────────────────────────────────────────
        header = tk.Frame(outer, bg=THEME.bg, padx=22, pady=20)
        header.pack(side="top", fill="x")
        IconButton(
            header, glyph="back", size=24,
            on_click=self.destroy, tooltip="Закрыть",
        ).pack(side="left")
        title_box = tk.Frame(header, bg=THEME.bg)
        title_box.pack(side="left", padx=(12, 0))
        tk.Label(
            title_box, text="ИНСТРУКЦИЯ",
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box, text="Telegram прокси / VC",
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 13, "bold"),
            anchor="w",
        ).pack(anchor="w")

        # ── footer ──────────────────────────────────────────────────
        footer = tk.Frame(outer, bg=THEME.bg, padx=22, pady=14)
        footer.pack(side="bottom", fill="x")
        tk.Frame(outer, bg=THEME.border, height=1).pack(side="bottom", fill="x")

        copy_btn = tk.Label(
            footer, text="  скопировать tg://proxy ссылку  ",
            fg=THEME.bg, bg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"),
            cursor="hand2", padx=18, pady=8,
        )
        copy_btn.pack(side="right")
        copy_btn.bind("<Button-1>", lambda _e: self._copy_link())
        copy_btn.bind("<Enter>", lambda _e: copy_btn.configure(bg=THEME.accent_dim))
        copy_btn.bind("<Leave>", lambda _e: copy_btn.configure(bg=THEME.accent))

        # ── scrollable body ─────────────────────────────────────────
        mid = tk.Frame(outer, bg=THEME.bg)
        mid.pack(side="top", fill="both", expand=True)

        canvas = tk.Canvas(mid, bg=THEME.bg, highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)

        body = tk.Frame(canvas, bg=THEME.bg, padx=22, pady=4)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")

        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(body_id, width=e.width))

        # mousewheel scroll — bind on the canvas itself and on every child
        # widget; bind_all + Enter/Leave ломается, когда курсор уходит на
        # дочерний виджет (Tk шлёт <Leave> на Toplevel и привязка снимается).
        def _on_wheel(e: tk.Event) -> int:
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

        # ── content sections ────────────────────────────────────────
        self._params_block(body)
        self._section(body, "Telegram Desktop (Windows / macOS / Linux)", _STEPS_DESKTOP)
        self._section(body, "Голосовые чаты и звонки", _STEPS_VOICE)

        tk.Frame(body, bg=THEME.bg, height=8).pack(fill="x")

        # после построения всего содержимого — перепривязать скролл к новым детям
        try:
            self._bind_wheel_recursive(self)
        except Exception:
            pass

    def _params_block(self, master: tk.Misc) -> None:
        host = self.cfg.get("proxy_host", "127.0.0.1")
        port = self.cfg.get("proxy_port", 1443)
        secret = self.cfg.get("proxy_secret", "")
        tg_link = f"tg://proxy?server={host}&port={port}&secret=dd{secret}"

        box = tk.Frame(master, bg=THEME.card, padx=14, pady=12)
        box.pack(fill="x", pady=(8, 14))
        tk.Label(
            box, text="ПАРАМЕТРЫ ВАШЕГО ПРОКСИ",
            fg=THEME.text_secondary, bg=THEME.card,
            font=(THEME.font_ui, 8, "bold"),
            anchor="w",
        ).pack(fill="x")

        def _row(label: str, value: str) -> None:
            row = tk.Frame(box, bg=THEME.card)
            row.pack(fill="x", pady=(6, 0))
            tk.Label(
                row, text=label,
                fg=THEME.text_muted, bg=THEME.card,
                font=(THEME.font_ui, 9), width=10, anchor="w",
            ).pack(side="left")
            v = tk.Entry(
                row,
                bg=THEME.card, fg=THEME.text_primary,
                font=(THEME.font_mono, 10),
                relief="flat", bd=0, highlightthickness=0,
                insertbackground=THEME.text_primary,
                readonlybackground=THEME.card,
                disabledbackground=THEME.card,
                disabledforeground=THEME.text_primary,
            )
            v.insert(0, value)
            v.configure(state="readonly")
            v.pack(side="left", fill="x", expand=True)

        _row("Сервер:", host)
        _row("Порт:", str(port))
        _row("Тип:", "MTPROTO (подходит и для VC)")
        _row("Секрет:", "dd" + str(secret))
        _row("Ссылка:", tg_link)

    def _section(self, master: tk.Misc, title: str, steps: list) -> None:
        tk.Label(
            master, text=title.upper(),
            fg=THEME.accent_dim, bg=THEME.bg,
            font=(THEME.font_ui, 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(10, 4))

        for head, body in steps:
            block = tk.Frame(master, bg=THEME.bg)
            block.pack(fill="x", pady=(0, 10))
            tk.Label(
                block, text=head,
                fg=THEME.text_primary, bg=THEME.bg,
                font=(THEME.font_ui, 10, "bold"),
                anchor="w", wraplength=460, justify="left",
            ).pack(fill="x")
            tk.Label(
                block, text=body,
                fg=THEME.text_secondary, bg=THEME.bg,
                font=(THEME.font_ui, 10),
                anchor="w", wraplength=460, justify="left",
            ).pack(fill="x", pady=(2, 0))

    def _copy_link(self) -> None:
        host = self.cfg.get("proxy_host", "127.0.0.1")
        port = self.cfg.get("proxy_port", 1443)
        secret = self.cfg.get("proxy_secret", "")
        link = f"tg://proxy?server={host}&port={port}&secret=dd{secret}"
        try:
            self.clipboard_clear()
            self.clipboard_append(link)
            self.update()
        except Exception:
            log.exception("clipboard failed")
