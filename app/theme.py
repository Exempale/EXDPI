"""Тема оформления — единый дизайн для всех экранов."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
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


THEME = Theme()
