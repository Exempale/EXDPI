"""Уведомления Windows (тосты).

Основной путь — через иконку в трее (pystray → Shell_NotifyIcon, на
Windows 10/11 показывается как нативный тост). Если трея нет — fallback
через PowerShell + WinRT ToastNotificationManager.

Использование:
    from . import notify
    notify.set_enabled(cfg.get("notifications_enabled", True))
    notify.register_tray(tray_controller)   # опционально
    notify.send("EXDPI", "Обход включён")

Все вызовы неблокирующие (fallback уходит в фоновый поток) и безопасные —
ошибки только логируются.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading


log = logging.getLogger("dpibypass.notify")

_enabled = True
_tray = None  # TrayController | None
_lock = threading.Lock()


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = bool(value)


def is_enabled() -> bool:
    return _enabled


def register_tray(tray) -> None:
    """Передать TrayController — уведомления пойдут через иконку трея."""
    global _tray
    with _lock:
        _tray = tray


def unregister_tray() -> None:
    global _tray
    with _lock:
        _tray = None


def send(message: str, title: str = "EXDPI") -> None:
    """Показать уведомление Windows. Тихий no-op, если выключено в настройках."""
    if not _enabled:
        return
    with _lock:
        tray = _tray
    if tray is not None:
        try:
            tray.notify(message, title)
            return
        except Exception:
            log.exception("tray notify failed, falling back")
    threading.Thread(
        target=_powershell_toast, args=(title, message),
        daemon=True, name="notify-toast",
    ).start()


def _powershell_toast(title: str, message: str) -> None:
    """Fallback-тост через WinRT (работает без сторонних модулей)."""
    if sys.platform != "win32":
        log.info("notify (no toast on %s): %s — %s", sys.platform, title, message)
        return

    def esc(s: str) -> str:
        return (
            str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
        )

    script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = @'
<toast><visual><binding template="ToastGeneric"><text>{esc(title)}</text><text>{esc(message)}</text></binding></visual></toast>
'@
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = New-Object Windows.UI.Notifications.ToastNotification($doc)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Exempale.EXDPI').Show($toast)
"""
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=15,
        )
    except Exception:
        log.exception("powershell toast failed")
