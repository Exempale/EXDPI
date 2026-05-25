"""Пресеты «готовых конфиг-листов» с доменами для zapret.

Идея: чтобы пользователь мог одним кликом переключиться между «играми»,
«соцсетями», «ИИ-сервисами» и т.п. — без ручной правки list-general-user.txt.

Источники пресетов:
    * builtin     — встроены в код (ai_defaults), не зависят от .txt-файлов;
    * blocklists/ — текстовые файлы рядом с repo root (включаются в .exe
                    через build.spec, путь определяется в paths.blocklists_root).

API:
    presets()             → List[Preset]      # все доступные пресеты
    by_id(id) → Preset|None
    load_domains(preset_id) → List[str]       # уже нормализованные домены
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from . import paths
from .config import DEFAULT_CUSTOM_DOMAINS, normalize_domain_list, parse_domains

log = logging.getLogger("dpibypass.presets")


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    description: str
    # Один из: "custom", "builtin", "file"
    source: str
    # Для source="file" — имя файла внутри blocklists/.
    filename: Optional[str] = None


# id "custom" сохраняется в config.json как маркер «пользовательский набор» —
# при выборе custom не происходит автозамены.
PRESETS: List[Preset] = [
    Preset(
        id="custom",
        label="Свой набор",
        description="Ручной список из поля ниже. Не перезаписывается пресетами.",
        source="custom",
    ),
    Preset(
        id="ai",
        label="ИИ-сервисы (дефолт)",
        description="ChatGPT, Claude, Devin, Gemini, Grok, Perplexity, HuggingFace.",
        source="builtin",
    ),
    Preset(
        id="games",
        label="Игры и стриминг",
        description="Discord (текст/голос), Steam, Epic, Battle.net, Riot, Roblox, Twitch.",
        source="file",
        filename="exdpi-games.txt",
    ),
    Preset(
        id="social",
        label="Социальные сети",
        description="X/Twitter, Instagram, Facebook, Reddit, TikTok и др.",
        source="file",
        filename="exdpi-social.txt",
    ),
    Preset(
        id="popular_ru",
        label="Популярное в РФ",
        description="ИИ, видео, мессенджеры, новости — частые блокировки у РФ-провайдеров.",
        source="file",
        filename="exdpi-popular-ru.txt",
    ),
]


def presets() -> List[Preset]:
    return list(PRESETS)


def by_id(preset_id: str) -> Optional[Preset]:
    for p in PRESETS:
        if p.id == preset_id:
            return p
    return None


def load_domains(preset_id: str) -> List[str]:
    """Загрузить домены пресета. Вернёт нормализованный список без дубликатов."""
    p = by_id(preset_id)
    if not p:
        return []
    if p.source == "custom":
        return []
    if p.source == "builtin" and p.id == "ai":
        return normalize_domain_list(DEFAULT_CUSTOM_DOMAINS)
    if p.source == "file" and p.filename:
        path = paths.blocklists_root() / p.filename
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            log.warning("preset file not found: %s", path)
            return []
        except Exception:
            log.exception("failed to read preset %s", path)
            return []
        return parse_domains(text)
    return []
