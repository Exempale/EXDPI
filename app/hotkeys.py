"""Глобальные горячие клавиши (Pro): ON/OFF обхода и показать/скрыть окно.

Реализация на Windows API (RegisterHotKey) через ctypes, без сторонних
библиотек: регистрируем скрытое message-only окно и крутим цикл сообщений в
фоне. Комбинации читаются из конфига на лету — перерегистрация происходит
при изменении, занятая комбинация ретраится на следующем такте.

Поддерживаемые комбинации: Ctrl/Alt/Shift/Win + буква/цифра, а также
F1..F24 (с модификатором или без). Буквы/цифры без модификатора запрещены —
такой хоткей перехватил бы клавишу во всей системе.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from typing import Callable, Dict, Optional, Tuple

log = logging.getLogger("dpibypass.hotkeys")

# Win32 constants
HWND_MESSAGE = ctypes.c_void_p(-3)
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
_VK_OFFSET_F1 = 0x70  # VK_F1

_HOTKEY_TOGGLE = 1    # вкл/выкл обхода
_HOTKEY_SHOWHIDE = 2  # показать/скрыть окно

_MOD_NAMES = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN,
}


def _fkey_vk(last: str) -> Optional[int]:
    """F7 → VK код, если last — валидное имя функциональной клавиши."""
    if last.startswith("F") and last[1:].isdigit():
        n = int(last[1:])
        if 1 <= n <= 24:
            return _VK_OFFSET_F1 + n - 1
    return None


def parse_combo(text: str) -> Optional[Tuple[int, int]]:
    """Разобрать "Ctrl+Alt+E" → (modifiers, vk). None — невалидно."""
    try:
        parts = [p.strip() for p in str(text or "").split("+") if p.strip()]
    except Exception:
        return None
    if not parts:
        return None
    mods = 0
    for p in parts[:-1]:
        m = _MOD_NAMES.get(p.lower())
        if m is None:
            return None
        mods |= m
    last = parts[-1].upper()
    if len(parts) == 1:
        # без модификатора разрешены только F1..F24
        vk = _fkey_vk(last)
        return (0, vk) if vk is not None else None
    if len(last) == 1 and last.isalnum():
        return (mods, ord(last))
    vk = _fkey_vk(last)
    if vk is not None:
        return (mods, vk)
    return None


class HotkeyManager:
    """Менеджер глобальных хоткеев на message-only окне."""

    def __init__(self, cfg, on_toggle: Callable[[], None],
                 on_showhide: Optional[Callable[[], None]] = None,
                 interval: float = 1.0) -> None:
        self.cfg = cfg
        self._on_toggle = on_toggle
        self._on_showhide = on_showhide
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd = None
        self._wndproc = None  # живая ctypes-обёртка: GC убьёт прокси иначе
        self._registered: Dict[int, Tuple[int, int]] = {}  # id → (mods, vk)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="pro-hotkeys")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ── внутреннее ───────────────────────────────────────────────────
    def _create_hidden_window(self) -> bool:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # WNDCLASSW в ctypes/wintypes нет — объявляем по спецификации WinAPI.
        # HCURSOR в wintypes отсутствует (это тот же HICON) — берём HICON.
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.wintypes.HINSTANCE),
                ("hIcon", ctypes.wintypes.HICON),
                ("hCursor", ctypes.wintypes.HICON),
                ("hbrBackground", ctypes.wintypes.HBRUSH),
                ("lpszMenuName", ctypes.wintypes.LPCWSTR),
                ("lpszClassName", ctypes.wintypes.LPCWSTR),
            ]

        # DefWindowProcW без argtypes падает на больших lparam
        user32.DefWindowProcW.argtypes = (
            ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        user32.DefWindowProcW.restype = ctypes.c_longlong

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_HOTKEY:
                try:
                    if int(wparam or 0) == _HOTKEY_SHOWHIDE and self._on_showhide:
                        self._on_showhide()
                    else:
                        self._on_toggle()
                except Exception:
                    log.exception("hotkey handler failed")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        # держим обёртку WNDPROC, а не сырую функцию: сырая вызовет TypeError
        # при регистрации, а обёртка без внешней ссылки — краш при первом
        # сообщении (libffi-замыкание соберёт GC после выхода из метода)
        self._wndproc = WNDPROC(wndproc)

        try:
            hinst = kernel32.GetModuleHandleW(None)
            class_name = "EXDPI_HotkeySink"
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = hinst
            wc.lpszClassName = class_name
            atom = user32.RegisterClassW(ctypes.byref(wc))
            if not atom:
                atom = user32.FindWindowW(class_name, None)
                if not atom:
                    return False
            hwnd = user32.CreateWindowExW(
                0, class_name, "exdpi-hk", 0, 0, 0, 0, 0,
                HWND_MESSAGE, None, hinst, None)
            if not hwnd:
                return False
            self._hwnd = hwnd
            return True
        except Exception:
            log.exception("hotkey window create failed")
            return False

    def _register(self, mods: int, vk: int, hotkey_id: int) -> bool:
        try:
            rc = ctypes.windll.user32.RegisterHotKey(self._hwnd, hotkey_id,
                                                     mods, vk)
            if rc:
                self._registered[hotkey_id] = (mods, vk)
                log.info("hotkey registered: id=%d mods=%x vk=%d",
                         hotkey_id, mods, vk)
                return True
            log.warning("RegisterHotKey id=%d failed (%s) — возможно, занято другой программой",
                        hotkey_id, ctypes.windll.kernel32.GetLastError())
            return False
        except Exception:
            log.exception("RegisterHotKey raised")
            return False

    def _unregister(self, hotkey_id: int) -> None:
        try:
            if self._hwnd:
                ctypes.windll.user32.UnregisterHotKey(self._hwnd, hotkey_id)
        except Exception:
            pass
        self._registered.pop(hotkey_id, None)

    def _run(self) -> None:
        if not self._create_hidden_window():
            log.warning("hotkeys: hidden window not created, disabled")
            return
        msg = ctypes.wintypes.MSG()
        cur: Dict[int, Tuple[int, int]] = {}

        while not self._stop.is_set():
            try:
                active = bool(self.cfg.get("pro_hotkeys_enabled", True))
                want = {
                    _HOTKEY_TOGGLE:
                        parse_combo(str(self.cfg.get("pro_hotkey_key", "Ctrl+Alt+E")))
                        if active else None,
                    _HOTKEY_SHOWHIDE:
                        parse_combo(str(self.cfg.get("pro_hotkey_show_key", "Ctrl+Alt+W")))
                        if active else None,
                }
                for hid, combo in want.items():
                    have = cur.get(hid)
                    if combo and combo != have:
                        # одну комбинацию на два хоткея не делим
                        if any(combo == c for h, c in cur.items() if h != hid):
                            continue
                        if have:
                            self._unregister(hid)
                        # cur обновляем только при успехе: занятая комбинация
                        # попытается встать снова на следующем такте
                        if self._register(combo[0], combo[1], hotkey_id=hid):
                            cur[hid] = combo
                    elif combo is None and have:
                        self._unregister(hid)
                        cur.pop(hid, None)
            except Exception:
                log.exception("hotkeys reconcile failed")

            # цикл сообщений с таймаутом (не блокируем остановку)
            deadline = time.time() + self._interval
            while time.time() < deadline and not self._stop.is_set():
                try:
                    if ctypes.windll.user32.PeekMessageW(
                            ctypes.byref(msg), None, 0, 0, 0x0001):
                        ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                        ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
                    else:
                        time.sleep(0.05)
                except Exception:
                    time.sleep(0.2)

        for hid in list(cur):
            self._unregister(hid)
        try:
            if self._hwnd:
                ctypes.windll.user32.DestroyWindow(self._hwnd)
        except Exception:
            pass
