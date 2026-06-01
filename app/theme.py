"""Тема оформления — единый дизайн для всех экранов.

Поддерживает несколько пресетов (тёмная/светлая/контрастная) с возможностью
переключения во время работы. Виджеты импортируют общий объект ``THEME`` и
читают его атрибуты — после ``apply_theme(name)`` объект мутируется на месте,
поэтому достаточно перерисовать UI.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Dict, List


@dataclass
class Theme:
    """Палитра одной темы. Поля совпадают между всеми пресетами."""

    name: str = "dark"

    bg: str = "#0E141A"
    bg_elev: str = "#141B22"
    card: str = "#1A222B"
    card_hover: str = "#1F2832"
    border: str = "#252E38"

    text_primary: str = "#E8EAED"
    text_secondary: str = "#7B8794"
    text_muted: str = "#4F5963"

    accent: str = "#A6D8C2"
    accent_dim: str = "#7DB89F"
    accent_dark: str = "#3F5C50"

    danger: str = "#E66464"
    danger_dim: str = "#7A3838"

    track_off: str = "#1B232C"
    track_on: str = "#5FB68F"
    knob_off: str = "#7C8794"
    knob_on: str = "#F2FBF6"

    font_ui: str = "Segoe UI"
    font_mono: str = "Consolas"


# ── пресеты ─────────────────────────────────────────────────────────────
_DARK = Theme(
    name="dark",
)

_LIGHT = Theme(
    name="light",
    bg="#F4F6FA",
    bg_elev="#EDEFF4",
    card="#FFFFFF",
    card_hover="#F0F2F7",
    border="#D6DAE2",
    text_primary="#1A222B",
    text_secondary="#5B6470",
    text_muted="#9098A3",
    accent="#3B8F70",
    accent_dim="#2C7459",
    accent_dark="#A6D8C2",
    danger="#C9434A",
    danger_dim="#E89A9D",
    track_off="#D6DAE2",
    track_on="#3B8F70",
    knob_off="#FFFFFF",
    knob_on="#FFFFFF",
)

THEMES: Dict[str, Theme] = {
    "dark": _DARK,
    "light": _LIGHT,
}


THEME_LABELS: Dict[str, str] = {
    "dark": "Тёмная",
    "light": "Светлая",
}


def available_themes() -> List[str]:
    return list(THEMES.keys())


def label_for(name: str) -> str:
    return THEME_LABELS.get(name, name)


# Изменяемый «активный» объект, который импортируют все модули UI.
# При смене темы мы НЕ создаём новый объект — обновляем поля на месте,
# чтобы все существующие ссылки на ``THEME`` подхватили новые цвета сразу.
THEME = replace(_DARK)


def apply_theme(name: str) -> Theme:
    """Применить пресет темы по имени. Мутирует общий объект ``THEME``."""
    preset = THEMES.get(name) or _DARK
    for f in fields(Theme):
        setattr(THEME, f.name, getattr(preset, f.name))
    return THEME
