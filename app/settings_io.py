"""Импорт / экспорт настроек EXDPI в JSON-файл.

Формат файла:
    {
      "app": "EXDPI",
      "format": 1,
      "version": "1.7.0",          # версия EXDPI, из которой экспортировали
      "exported_at": "2026-06-10T12:00:00",
      "config": { ...config.json... }
    }

При импорте каждый ключ валидируется по типу и допустимым значениям —
незнакомые или битые ключи тихо отбрасываются (возвращаются в списке
``skipped`` для показа пользователю).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from . import __version__
from .config import GAME_MODES, normalize_domain_list
from .theme import available_themes

log = logging.getLogger("dpibypass.settings_io")

FORMAT_VERSION = 1
FILE_EXT = ".exdpi.json"


def _is_port(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 65535


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_host(v: Any) -> bool:
    if not isinstance(v, str) or not v:
        return False
    parts = v.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _is_secret(v: Any) -> bool:
    if not isinstance(v, str) or len(v) != 32:
        return False
    try:
        int(v, 16)
        return True
    except ValueError:
        return False


def _is_str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ключ → (валидатор, нормализатор | None)
_VALIDATORS: Dict[str, Tuple[Callable[[Any], bool], Any]] = {
    # proxy
    "proxy_enabled": (_is_bool, None),
    "proxy_port": (_is_port, None),
    "proxy_host": (_is_host, None),
    "proxy_secret": (_is_secret, None),
    "proxy_dc_ip": (_is_str_list, None),
    # zapret
    "zapret_enabled": (_is_bool, None),
    "zapret_strategy": (_is_str, None),
    "zapret_strategy_auto_result": (_is_str, None),
    "custom_domains": (_is_str_list, normalize_domain_list),
    "domain_preset": (_is_str, None),
    "game_mode": (lambda v: v in GAME_MODES, None),
    # secure dns
    "securedns_enabled": (_is_bool, None),
    "securedns_protocol": (lambda v: v in ("doh", "dot"), None),
    "securedns_provider": (_is_str, None),
    "securedns_set_system": (_is_bool, None),
    # general
    "autostart_with_windows": (_is_bool, None),
    "minimize_to_tray": (_is_bool, None),
    "start_minimized": (_is_bool, None),
    "notifications_enabled": (_is_bool, None),
    "theme": (lambda v: v in available_themes(), None),
    "wizard_done": (_is_bool, None),
    "update_skip_until": (_is_number, None),
}


@dataclass
class ImportResult:
    """Итог импорта: что применилось, что отброшено, ошибка (если была)."""

    ok: bool
    applied: Dict[str, Any] = field(default_factory=dict)
    skipped: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def applied_count(self) -> int:
        return len(self.applied)


def export_settings(cfg: Dict[str, Any], path: Path) -> bool:
    """Сохранить настройки в JSON-файл. True при успехе."""
    payload = {
        "app": "EXDPI",
        "format": FORMAT_VERSION,
        "version": __version__,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "config": {k: cfg[k] for k in sorted(_VALIDATORS) if k in cfg},
    }
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False)
        log.info("settings exported to %s (%d keys)", path, len(payload["config"]))
        return True
    except Exception:
        log.exception("export failed")
        return False


def import_settings(path: Path) -> ImportResult:
    """Прочитать и провалидировать файл настроек.

    Возвращает ImportResult: ``applied`` — словарь валидных ключей для
    cfg.update(...), ``skipped`` — отброшенные ключи.
    """
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except FileNotFoundError:
        return ImportResult(ok=False, error="Файл не найден.")
    except json.JSONDecodeError as exc:
        return ImportResult(ok=False, error=f"Файл повреждён (не JSON): {exc}")
    except Exception as exc:
        return ImportResult(ok=False, error=f"Не удалось прочитать файл: {exc}")

    if not isinstance(data, dict):
        return ImportResult(ok=False, error="Неверный формат файла.")

    # поддерживаем и «голый» config.json, и наш формат-обёртку
    config = data.get("config") if isinstance(data.get("config"), dict) else data
    if data.get("app") not in (None, "EXDPI"):
        return ImportResult(ok=False, error="Это файл настроек другой программы.")
    if not isinstance(config, dict) or not config:
        return ImportResult(ok=False, error="В файле нет настроек.")

    applied: Dict[str, Any] = {}
    skipped: List[str] = []
    for key, value in config.items():
        rule = _VALIDATORS.get(key)
        if rule is None:
            skipped.append(key)
            continue
        validator, normalizer = rule
        try:
            if not validator(value):
                skipped.append(key)
                continue
            applied[key] = normalizer(value) if normalizer else value
        except Exception:
            skipped.append(key)

    if not applied:
        return ImportResult(ok=False, error="Ни одной валидной настройки в файле.", skipped=skipped)

    log.info("settings import: %d applied, %d skipped", len(applied), len(skipped))
    return ImportResult(ok=True, applied=applied, skipped=skipped)


def default_export_filename() -> str:
    return f"exdpi-settings-{datetime.now():%Y%m%d-%H%M}{FILE_EXT}"
