"""Поиск ресурсов (bin/, lists/, icon) в dev и onefile-режимах PyInstaller."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidates() -> list[Path]:
    out: list[Path] = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        out.append(Path(mei))
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent)
    out.append(Path(__file__).resolve().parent.parent)
    return out


def resource_root() -> Path:
    for c in _candidates():
        if (c / "resources").is_dir():
            return c / "resources"
    return _candidates()[0] / "resources"


def zapret_root() -> Path:
    return resource_root() / "zapret"


def zapret_bin() -> Path:
    return zapret_root() / "bin"


def zapret_lists() -> Path:
    return zapret_root() / "lists"


def service_bat() -> Path:
    """Путь к service.bat zapret (диспетчер/меню оригинального zapret)."""
    return zapret_root() / "service.bat"


def easter_image() -> Path:
    """Картинка-пасхалка (resources/easter/1.jpg). Бандлится через build.spec."""
    return resource_root() / "easter" / "1.jpg"


def banner_image() -> Path:
    """Рекламный баннер (resources/banner.jpg) для VPN-режима.

    Бандлится через build.spec рядом с icon.png / easter.
    """
    return resource_root() / "banner.jpg"


def singbox_root() -> Path:
    """Папка с ядром Sing-box (resources/singbox/sing-box.exe)."""
    return resource_root() / "singbox"


def singbox_binary() -> Path:
    """Исполняемый файл sing-box.exe."""
    return singbox_root() / "sing-box.exe"


def singbox_config_path() -> Path:
    """Куда класть сгенерированный singbox_config.json.

    Лежит в %APPDATA%/EXDPI рядом с config.json — туда можно писать и в
    dev-режиме, и в onefile-сборке (в _MEIPASS писать нельзя).
    """
    from .config import app_dir
    return app_dir() / "singbox_config.json"


def icon_ico() -> Path:
    p = resource_root() / "icon.ico"
    return p


def icon_png() -> Path:
    return resource_root() / "icon.png"


def blocklists_root() -> Path:
    """Папка с пресетами доменов (blocklists/*.txt).

    Лежит рядом с resources/ — в dev-режиме это корень репо, в onefile-сборке
    она кладётся в _MEIPASS через build.spec (см. data-include).
    """
    for c in _candidates():
        p = c / "blocklists"
        if p.is_dir():
            return p
    return _candidates()[0] / "blocklists"
