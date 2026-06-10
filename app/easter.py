"""Пасхалка EXDPI: по нажатию открывается прикольная картинка :D

Картинка лежит в resources/easter/1.jpg (бандлится через build.spec).
Открывается в отдельном безрамочном окошке поверх приложения. Если по
какой-то причине картинка недоступна — тихо открываем системным просмотрщиком
либо ничего не делаем (пасхалка не должна ронять приложение).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
from typing import Optional

from . import paths
from .theme import THEME

log = logging.getLogger("dpibypass.easter")

# держим ссылку на PhotoImage, иначе Tk соберёт её сборщиком мусора и окно
# покажет пустоту.
_IMG_REF = None  # type: ignore[var-annotated]
_OPEN_WIN: Optional[tk.Toplevel] = None


def _open_external(path) -> None:
    """Fallback: открыть картинку системным просмотрщиком."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        log.exception("easter: external open failed")


def show_easter_egg(master: Optional[tk.Misc] = None) -> bool:
    """Показать картинку-пасхалку. Возвращает True при успехе.

    При повторном вызове переоткрывает окно (закрывает предыдущее).
    """
    global _IMG_REF, _OPEN_WIN

    img_path = paths.easter_image()
    if not img_path.exists():
        log.warning("easter image not found: %s", img_path)
        return False

    # нет Tk-рута (например, вызов вне UI) — открываем системно.
    if master is None:
        _open_external(img_path)
        return True

    # закрыть прошлое окно пасхалки, если оно ещё открыто
    try:
        if _OPEN_WIN is not None and _OPEN_WIN.winfo_exists():
            _OPEN_WIN.destroy()
    except Exception:
        pass
    _OPEN_WIN = None

    try:
        from PIL import Image, ImageTk
    except Exception:
        # без Pillow не отрисуем в Tk — fallback на системный просмотрщик
        _open_external(img_path)
        return True

    try:
        img = Image.open(str(img_path))
        img.load()
    except Exception:
        log.exception("easter: failed to open image")
        _open_external(img_path)
        return True

    # масштабируем под экран (не больше ~70% высоты), сохраняя пропорции
    try:
        screen_h = master.winfo_screenheight()
        screen_w = master.winfo_screenwidth()
    except Exception:
        screen_h, screen_w = 800, 1200
    max_h = int(screen_h * 0.7)
    max_w = int(screen_w * 0.7)
    w, h = img.size
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        try:
            resample = Image.Resampling.LANCZOS  # Pillow >= 9.1
        except AttributeError:  # pragma: no cover
            resample = Image.LANCZOS  # type: ignore[attr-defined]
        img = img.resize(new_size, resample)

    win = tk.Toplevel(master)
    win.title("EXDPI :D")
    win.configure(bg=THEME.bg)
    win.resizable(False, False)
    try:
        win.transient(master.winfo_toplevel())
    except Exception:
        pass

    try:
        _IMG_REF = ImageTk.PhotoImage(img)
    except Exception:
        log.exception("easter: PhotoImage failed")
        win.destroy()
        _open_external(img_path)
        return True

    holder = tk.Frame(win, bg=THEME.bg, padx=10, pady=10)
    holder.pack(fill="both", expand=True)
    lbl = tk.Label(holder, image=_IMG_REF, bg=THEME.bg, bd=0, cursor="hand2")
    lbl.pack()
    tk.Label(
        holder, text="ты нашёл пасхалку :D   ·   EXDPI by Exempale",
        fg=THEME.text_muted, bg=THEME.bg, font=(THEME.font_ui, 9),
    ).pack(pady=(8, 0))

    # клик по картинке / Esc — закрыть
    lbl.bind("<Button-1>", lambda _e: win.destroy())
    win.bind("<Escape>", lambda _e: win.destroy())

    # центрируем окно
    win.update_idletasks()
    ww = win.winfo_reqwidth()
    wh = win.winfo_reqheight()
    try:
        mx = master.winfo_rootx()
        my = master.winfo_rooty()
        mw = master.winfo_width()
        mh = master.winfo_height()
        x = mx + (mw - ww) // 2
        y = my + (mh - wh) // 2
    except Exception:
        x = (screen_w - ww) // 2
        y = (screen_h - wh) // 2
    x = max(10, min(x, screen_w - ww - 10))
    y = max(10, min(y, screen_h - wh - 40))
    win.geometry(f"+{x}+{y}")

    try:
        ico = paths.icon_ico()
        if ico.exists():
            win.iconbitmap(str(ico))
    except Exception:
        pass

    _OPEN_WIN = win
    try:
        win.lift()
        win.focus_force()
    except Exception:
        pass
    return True
