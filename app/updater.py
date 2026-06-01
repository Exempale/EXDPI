"""Авто-проверка обновлений через GitHub Releases API."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import tkinter as tk
import webbrowser
from typing import Callable, Dict, List, Optional, Tuple
from urllib import request as urlrequest
from urllib.error import URLError

from . import GITHUB_RELEASES_URL, GITHUB_REPO, __version__
from . import paths
from .theme import THEME
from .widgets import IconButton

log = logging.getLogger("dpibypass.updater")


GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
SKIP_DURATION_SECONDS = 3 * 24 * 60 * 60


# ── version helpers ──────────────────────────────────────────────────


def _parse_version(raw: Optional[str]) -> Optional[Tuple[int, ...]]:
    """Превратить '1.2.3' / 'v1.2.3-beta' / 'EXDPI 1.3' в кортеж интов.

    Возвращает None, если не удалось распарсить.
    """
    if not raw:
        return None
    m = re.search(r"(\d+(?:\.\d+){0,5})", str(raw))
    if not m:
        return None
    try:
        parts = tuple(int(p) for p in m.group(1).split("."))
    except ValueError:
        return None
    return parts or None


def _is_newer(remote: Optional[str], local: Optional[str]) -> bool:
    r = _parse_version(remote)
    l = _parse_version(local)
    if r is None or l is None:
        return False
    # выровнять длины нулями
    n = max(len(r), len(l))
    r = r + (0,) * (n - len(r))
    l = l + (0,) * (n - len(l))
    return r > l


def is_mandatory(remote: Optional[str]) -> bool:
    """Обязательное ли это обновление?

    Правило: если PATCH-часть (последний значащий компонент) версии равна 0
    — например 1.5.0, 2.0.0 — обновление обязательно. Иначе (1.5.1, 1.5.9)
    необязательно. Берём третью цифру; если её нет, считаем 0 (обязательно).
    """
    parts = _parse_version(remote)
    if not parts:
        return False
    patch = parts[2] if len(parts) >= 3 else 0
    return patch == 0


# ── network ──────────────────────────────────────────────────────────


def _fetch_latest_release() -> Optional[Dict[str, str]]:
    req = urlrequest.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"EXDPI/{__version__}",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=8) as resp:
            data = resp.read()
    except (URLError, TimeoutError, OSError) as exc:
        log.debug("update check failed: %s", exc)
        return None
    try:
        obj = json.loads(data)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    tag = obj.get("tag_name") or obj.get("name")
    html_url = obj.get("html_url") or GITHUB_RELEASES_URL
    body = obj.get("body") or ""
    return {
        "tag": str(tag) if tag else "",
        "url": str(html_url),
        "body": str(body)[:500],
    }


# ── public API ───────────────────────────────────────────────────────


def should_check_now(cfg: Dict) -> bool:
    """Проверять ли сейчас? Учитываем 'отложено на 3 дня'."""
    skip_until = cfg.get("update_skip_until", 0)
    try:
        skip_until = float(skip_until)
    except (TypeError, ValueError):
        skip_until = 0
    return time.time() >= skip_until


def check_async(
    cfg: Dict,
    on_update_available: Callable[[Dict[str, str]], None],
) -> None:
    """Запустить фоновую проверку. Если есть новая версия — вызовет колбэк
    с release_info из GitHub. Колбэк вызывается из фонового потока, поэтому
    UI-код должен сам обернуть свои действия в `root.after(0, ...)`.
    """
    if not should_check_now(cfg):
        return

    def _work():
        info = _fetch_latest_release()
        if not info:
            return
        if _is_newer(info["tag"], __version__):
            try:
                on_update_available(info)
            except Exception:
                log.exception("update callback raised")

    threading.Thread(target=_work, daemon=True, name="update-check").start()


def snooze_for_three_days(cfg: Dict) -> None:
    cfg["update_skip_until"] = int(time.time() + SKIP_DURATION_SECONDS)


# ── UI ───────────────────────────────────────────────────────────────


class UpdateDialog(tk.Toplevel):
    """Диалог уведомления о новой версии — в стиле приложения."""

    WIDTH = 400
    HEIGHT = 280

    def __init__(
        self,
        master: tk.Misc,
        info: Dict[str, str],
        on_skip: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self._info = info
        self._on_skip = on_skip
        self._mandatory = is_mandatory(info.get("tag"))
        self._master = master

        self.title("EXDPI · обновление")
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
        self.update_idletasks()

        # центрируем относительно master
        try:
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
            mh = master.winfo_height()
        except Exception:
            mx = my = 0
            mw = mh = 0
        w = max(self.WIDTH, self.winfo_reqwidth())
        h = max(self.HEIGHT, self.winfo_reqheight())
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = mx + (mw - w) // 2 if mw else (screen_w - w) // 2
        y = my + (mh - h) // 2 if mh else (screen_h - h) // 2
        x = max(10, min(x, screen_w - w - 10))
        y = max(10, min(y, screen_h - h - 60))
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Обязательное обновление: крестик и Esc закрывают приложение целиком.
        # Необязательное — обычное «отложить на 3 дня».
        if self._mandatory:
            self.protocol("WM_DELETE_WINDOW", self._force_quit)
            self.bind("<Escape>", lambda _e: self._force_quit())
        else:
            self.protocol("WM_DELETE_WINDOW", self._skip)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=THEME.bg, padx=24, pady=22)
        outer.pack(fill="both", expand=True)

        # header
        header = tk.Frame(outer, bg=THEME.bg)
        header.pack(fill="x")
        if not self._mandatory:
            IconButton(
                header, glyph="back", size=24,
                on_click=self._skip, tooltip="Закрыть",
            ).pack(side="left")
            title_pad = (12, 0)
        else:
            title_pad = (0, 0)
        title_box = tk.Frame(header, bg=THEME.bg)
        title_box.pack(side="left", padx=title_pad)
        tk.Label(
            title_box,
            text="ОБЯЗАТЕЛЬНОЕ ОБНОВЛЕНИЕ" if self._mandatory else "ОБНОВЛЕНИЕ",
            fg=THEME.danger if self._mandatory else THEME.text_secondary,
            bg=THEME.bg,
            font=(THEME.font_ui, 8, "bold"), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box, text="EXDPI",
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 13, "bold"), anchor="w",
        ).pack(anchor="w")

        # body
        body = tk.Frame(outer, bg=THEME.bg)
        body.pack(fill="both", expand=True, pady=(20, 0))

        tag = self._info.get("tag", "?")
        tk.Label(
            body,
            text="Вышла новая версия",
            fg=THEME.text_primary, bg=THEME.bg,
            font=(THEME.font_ui, 14, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            body,
            text=f"EXDPI {tag}  ·  у тебя {__version__}",
            fg=THEME.accent_dim, bg=THEME.bg,
            font=(THEME.font_ui, 10, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        if self._mandatory:
            body_text = (
                "Это обязательное обновление — пропустить его нельзя.\n"
                "Откройте страницу релиза, скачайте новый EXDPI.exe\n"
                "и замените старый. Без обновления программа закроется."
            )
        else:
            body_text = (
                "Откройте страницу релиза, скачайте новый EXDPI.exe\n"
                "и замените старый."
            )
        tk.Label(
            body, text=body_text,
            fg=THEME.text_secondary, bg=THEME.bg,
            font=(THEME.font_ui, 10),
            anchor="w", justify="left", wraplength=340,
        ).pack(anchor="w", pady=(12, 0))

        link = tk.Label(
            body,
            text=self._info.get("url", GITHUB_RELEASES_URL),
            fg=THEME.accent_dim, bg=THEME.bg,
            font=(THEME.font_ui, 9, "underline"),
            cursor="hand2", anchor="w",
            wraplength=340, justify="left",
        )
        link.pack(anchor="w", pady=(8, 0))
        link.bind("<Button-1>", lambda _e: self._open_release())

        # footer (buttons)
        footer = tk.Frame(outer, bg=THEME.bg)
        footer.pack(side="bottom", fill="x", pady=(16, 0))

        if not self._mandatory:
            skip = tk.Label(
                footer, text="пропустить обновление",
                fg=THEME.text_secondary, bg=THEME.bg,
                font=(THEME.font_ui, 10), cursor="hand2",
            )
            skip.pack(side="left", padx=(2, 0))
            skip.bind("<Button-1>", lambda _e: self._skip())
        else:
            quit_lbl = tk.Label(
                footer, text="закрыть программу",
                fg=THEME.danger_dim, bg=THEME.bg,
                font=(THEME.font_ui, 10), cursor="hand2",
            )
            quit_lbl.pack(side="left", padx=(2, 0))
            quit_lbl.bind("<Button-1>", lambda _e: self._force_quit())

        open_btn = tk.Label(
            footer, text="  открыть страницу релиза  ",
            fg=THEME.bg, bg=THEME.accent,
            font=(THEME.font_ui, 10, "bold"),
            cursor="hand2", padx=14, pady=8,
        )
        open_btn.pack(side="right")
        open_btn.bind("<Button-1>", lambda _e: self._open_release())
        open_btn.bind("<Enter>", lambda _e: open_btn.configure(bg=THEME.accent_dim))
        open_btn.bind("<Leave>", lambda _e: open_btn.configure(bg=THEME.accent))

    def _open_release(self) -> None:
        url = self._info.get("url") or GITHUB_RELEASES_URL
        try:
            webbrowser.open(url, new=2)
        except Exception:
            log.exception("failed to open release URL")
        # после открытия страницы — закрываем диалог.
        # В обязательном режиме также завершаем приложение, чтобы
        # пользователь точно скачал и установил новую версию.
        if self._mandatory:
            self._force_quit()
            return
        try:
            self.destroy()
        except Exception:
            pass

    def _force_quit(self) -> None:
        """Обязательное обновление: закрытие диалога завершает программу."""
        try:
            self.destroy()
        except Exception:
            pass
        # пытаемся аккуратно закрыть главное окно
        try:
            quit_fn = getattr(self._master, "_quit_app", None)
            if callable(quit_fn):
                quit_fn()
                return
            self._master.destroy()
        except Exception:
            log.exception("force quit failed")

    def _skip(self) -> None:
        try:
            self._on_skip()
        except Exception:
            log.exception("on_skip failed")
        try:
            self.destroy()
        except Exception:
            pass
