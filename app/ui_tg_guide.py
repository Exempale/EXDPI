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
    ("1. Откройте Telegram Desktop",
     "В программе перейдите в «Настройки» → «Продвинутые настройки» → "
     "«Тип соединения»."),
    ("2. Выберите «Использовать пользовательский прокси»",
     "В появившемся окне нажмите «Добавить прокси» → выберите тип "
     "«MTPROTO». Это та же опция, что подходит для голосовых "
     "чатов (Voice Chats / VC)."),
    ("3. Вставьте параметры подключения",
     "Сервер: localhost (или 127.0.0.1). Порт: тот, что указан в EXDPI "
     "(по умолчанию 1443). Секрет: 32-hex значение из настроек EXDPI."),
    ("4. Проще: скопируйте готовую ссылку",
     "Вернитесь в главное окно EXDPI и кликните по 📋 рядом с "
     "«mtproto · 127.0.0.1:…». Затем в Telegram → «Настройки» → "
     "«Продвинутые» → «Использовать пользовательский прокси» → "
     "вставьте tg://proxy?… — клиент сам подставит поля."),
    ("5. Включите EXDPI и проверьте",
     "Нажмите большой переключатель ON. В Telegram Desktop в правом "
     "верхнем углу должна появиться зелёная иконка прокси."),
]

_STEPS_MOBILE = [
    ("Android / iOS",
     "Откройте EXDPI на компьютере, скопируйте tg://proxy-ссылку (📋 в "
     "главном окне) и отправьте её себе в Saved Messages. Тапните по "
     "ссылке в мобильном Telegram — он сам предложит «Подключиться к "
     "прокси». Учтите: телефон должен быть в одной локальной сети с "
     "компьютером и видеть его IP, а в настройках EXDPI замените "
     "хост 127.0.0.1 на локальный IP машины (например 192.168.0.5)."),
]

_STEPS_VOICE = [
    ("Голосовые чаты (VC) и звонки",
     "Telegram использует тот же прокси и для текста, и для voice chat. "
     "Никакой отдельной настройки внутри Voice Chat не нужно — достаточно, "
     "чтобы основной MTProto-прокси (localhost:порт) был активен. Если "
     "вас не слышно/собеседника не слышно: обычно проблема в стратегии "
     "zapret. В настройках попробуйте general (ALT10) → general (FAKE TLS "
     "AUTO) → general (SIMPLE FAKE). Запасной вариант — включить «гейминг» "
     "режим (он расширяет фильтр на высокие UDP-порты, через которые "
     "ходит голос)."),
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
        req_h = min(self.HEIGHT, max(460, sh - 120))
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

        # mousewheel scroll
        def _on_wheel(e: tk.Event) -> None:
            try:
                delta = int(-1 * (e.delta / 120))
            except Exception:
                delta = -1 if getattr(e, "num", 0) == 4 else 1
            canvas.yview_scroll(delta, "units")

        def _bind_wheel(_e: tk.Event) -> None:
            canvas.bind_all("<MouseWheel>", _on_wheel)
            canvas.bind_all("<Button-4>", _on_wheel)
            canvas.bind_all("<Button-5>", _on_wheel)

        def _unbind_wheel(_e: tk.Event) -> None:
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass

        self.bind("<Enter>", _bind_wheel)
        self.bind("<Leave>", _unbind_wheel)
        self.bind("<Destroy>", lambda _e: _unbind_wheel(_e))

        # ── content sections ────────────────────────────────────────
        self._params_block(body)
        self._section(body, "Telegram Desktop (Windows / macOS / Linux)", _STEPS_DESKTOP)
        self._section(body, "На телефоне", _STEPS_MOBILE)
        self._section(body, "Голосовые чаты и звонки", _STEPS_VOICE)

        tk.Frame(body, bg=THEME.bg, height=8).pack(fill="x")

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
