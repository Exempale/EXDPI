"""Авто-запуск EXDPI вместе с Windows.

Через ключ реестра HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
Этот вариант чище shell:startup: применяется без перелогина, не требует
прав администратора (HKCU), убирается одним удалением значения.

На не-Windows платформах все функции — no-op.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("dpibypass.autostart")


_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "EXDPI"


def _exe_path() -> Optional[str]:
    """Путь к .exe, который пишем в реестр.

    В onefile-сборке PyInstaller это сам EXDPI.exe (sys.executable).
    В development-режиме (запуск из python) возвращаем None, чтобы не
    регистрировать python.exe в автозагрузке случайно.
    """
    if not getattr(sys, "frozen", False):
        return None
    exe = sys.executable
    try:
        return str(Path(exe).resolve())
    except Exception:
        return exe


def _open_run_key():
    """Открыть HKCU\\...\\Run на запись. Возвращает (winreg, key) или None."""
    if sys.platform != "win32":
        return None
    try:
        import winreg  # type: ignore
    except ImportError:
        return None
    try:
        key = winreg.OpenKeyEx(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY_PATH,
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )
        return winreg, key
    except OSError as exc:
        log.warning("failed to open Run key: %s", exc)
        return None


def is_enabled() -> bool:
    """True, если в реестре есть наша запись и она указывает на текущий .exe."""
    pair = _open_run_key()
    if pair is None:
        return False
    winreg, key = pair
    try:
        try:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
        except FileNotFoundError:
            return False
        if not value:
            return False
        # сравнение «без кавычек», на всякий
        cur = str(value).strip().strip('"').lower()
        target = (_exe_path() or "").lower()
        if not target:
            # frozen=False — просто факт того, что запись есть
            return True
        return cur == target
    finally:
        try:
            winreg.CloseKey(key)
        except Exception:
            pass


def enable() -> bool:
    """Создать/обновить запись автозапуска. Возвращает True при успехе."""
    pair = _open_run_key()
    if pair is None:
        log.info("autostart enable skipped: not on Windows or winreg unavailable")
        return False
    winreg, key = pair
    exe = _exe_path()
    if not exe:
        log.info("autostart enable skipped: not running from frozen exe")
        try:
            winreg.CloseKey(key)
        except Exception:
            pass
        return False
    # quote path с пробелами
    value = f'"{exe}"' if " " in exe else exe
    try:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, value)
        log.info("autostart enabled: %s", value)
        return True
    except OSError as exc:
        log.warning("failed to set autostart: %s", exc)
        return False
    finally:
        try:
            winreg.CloseKey(key)
        except Exception:
            pass


def disable() -> bool:
    """Удалить запись автозапуска. Возвращает True при успехе или
    если записи не было."""
    pair = _open_run_key()
    if pair is None:
        return False
    winreg, key = pair
    try:
        try:
            winreg.DeleteValue(key, _VALUE_NAME)
            log.info("autostart disabled")
        except FileNotFoundError:
            pass
        return True
    except OSError as exc:
        log.warning("failed to remove autostart: %s", exc)
        return False
    finally:
        try:
            winreg.CloseKey(key)
        except Exception:
            pass


def apply(want_enabled: bool) -> None:
    """Привести состояние реестра к заданному. Тихо, ошибки логируются."""
    try:
        if want_enabled:
            if not is_enabled():
                enable()
        else:
            if is_enabled():
                disable()
    except Exception:
        log.exception("autostart apply failed")
