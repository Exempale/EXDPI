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
