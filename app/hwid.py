"""Идентификатор устройства (HWID) для подписок с привязкой к устройству.

Некоторые VPN-сервисы (панели Remnawave и подобные) отдают реальный конфиг
только клиентам, которые передают HWID устройства в HTTP-заголовке
``x-hwid``. Без него сервис возвращает заглушку («App not supported / Please
use Happ») с фиктивными серверами ``0.0.0.0:1``.

HWID вычисляется один раз и кэшируется. Источники по приоритету:

1. ``HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid`` — стабильный
   per-install идентификатор Windows (постоянен до переустановки ОС).
2. MAC-адрес сетевого адаптера (``uuid.getnode``) — fallback.

Итоговое значение — детерминированный UUIDv5 в виде строки (совпадает по
формату с тем, что шлют v2rayNG/Happ).
"""
from __future__ import annotations

import logging
import uuid

log = logging.getLogger("dpibypass.hwid")

# RFC 4122 namespace (namespace_dns) — фиксированный, чтобы HWID был
# детерминированным между запусками на одной машине.
_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
_cached = None  # type: str | None


def _machine_guid() -> str:
    """MachineGuid из реестра Windows, либо пустая строка (не Windows/нет доступа)."""
    try:
        import winreg  # только Windows
    except Exception:
        return ""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        try:
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(val).strip()
        finally:
            winreg.CloseKey(key)
    except Exception:
        return ""


def _raw_source() -> str:
    guid = _machine_guid()
    if guid:
        return "machineguid:" + guid
    # fallback — MAC-адрес адаптера (48 бит). На реальном железе стабилен.
    return "mac:" + format(uuid.getnode(), "012x")


def device_hwid() -> str:
    """Стабильный HWID устройства как UUID-строка. Результат кэшируется."""
    global _cached
    if _cached is not None:
        return _cached
    try:
        _cached = str(uuid.uuid5(_NAMESPACE, _raw_source()))
    except Exception:
        log.warning("не удалось вычислить HWID, используем случайный", exc_info=True)
        _cached = str(uuid.uuid4())
    return _cached


def device_headers() -> dict:
    """HTTP-заголовки устройства для запроса подписки (нужны панелям с HWID-привязкой)."""
    return {
        "x-hwid": device_hwid(),
        "x-device-os": "windows",
        "x-ver-os": "11",
        "x-device-model": "PC",
    }
