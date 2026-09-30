"""Облачные стратегии: автообновление general*.bat из манифеста.

Манифест — JSON по URL из ``app.STRATEGY_MANIFEST_URL``:

    {
      "version": "1.3",
      "strategies": [
        "https://raw.githubusercontent.com/YOU/exdpi-strategies/main/general (ALT).bat",
        "https://raw.githubusercontent.com/YOU/exdpi-strategies/main/general (FAKE TLS AUTO).bat",
        ...
      ]
    }

Приличия:
  * скачиваются только .bat в папку ``%APPDATA%\\EXDPI\\strategies``
    (приоритет над встроенными — см. zapret_runner.resolve_strategy_file);
  * применяются, только если версия манифеста отличается от последней
    применённой (cfg["pro_strategy_cloud_ver"]) и Pro-лицензия активна;
  * недоступность сети — не ошибка: повторяем в следующий раз.
"""
from __future__ import annotations

import json
import logging
import threading
import urllib.request
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse, unquote

from . import zapret_runner
from . import STRATEGY_MANIFEST_URL

log = logging.getLogger("dpibypass.strategy_cloud")


def _fetch(url: str, timeout: float = 12.0) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EXDPI/"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        log.debug("strategy_cloud fetch failed: %s", url, exc_info=True)
        return None


def _bat_name(url: str) -> Optional[str]:
    """Имя .bat-файла из URL: декодируем %xx и отбраковываем опасные пути.

    Возвращает None для всего, что не general*.bat или содержит путь —
    движок запускает только general*.bat (см. zapret_runner), а писать
    файлы с '..' или разделителями папок недопустимо.
    """
    name = unquote(urlparse(str(url)).path.rstrip("/").rsplit("/", 1)[-1])
    if not name.lower().endswith(".bat") or not name.lower().startswith("general"):
        return None
    if any(s in name for s in ("/", "\\", "..", "\x00")):
        return None
    return name


def apply_cloud_strategies(cfg) -> Tuple[bool, str]:
    """Попробовать применить облачные стратегии. Возвращает (changed, message).

    Вызывается в фоне. Ничего не делает, если фича выключена, лицензия
    неактивна или манифест-URL не настроен.
    """
    if not bool(cfg.get("pro_strategy_cloud_enabled", True)):
        return False, "Облачные стратегии отключены в настройках."
    url = STRATEGY_MANIFEST_URL or ""
    if not url:
        return False, "Манифест стратегий не настроен (STRATEGY_MANIFEST_URL)."

    raw = _fetch(url)
    if raw is None:
        return False, "Сервер стратегий недоступен (повторю позже)."
    try:
        manifest = json.loads(raw.decode("utf-8"))
        version = str(manifest.get("version", ""))
        strategy_urls = []
        for u in manifest.get("strategies", []):
            u = str(u)
            if not u.startswith("http"):
                continue
            if _bat_name(u):
                strategy_urls.append(u)
    except Exception:
        log.exception("strategy_cloud manifest parse failed")
        return False, "Манифест стратегий повреждён."

    if not strategy_urls:
        return False, "В манифесте нет подходящих стратегий general*.bat."

    if str(cfg.get("pro_strategy_cloud_ver")) == version:
        return False, ""

    out_dir = zapret_runner.strategies_override_dir()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log.exception("cannot create strategies dir")
        return False, "Нет доступа к папке стратегий."

    applied = 0
    for u in strategy_urls:
        name = _bat_name(u)
        if not name:
            continue
        data = _fetch(u)
        if data is None:
            continue
        try:
            (out_dir / name).write_bytes(data)
            applied += 1
        except Exception:
            log.exception("strategy write failed: %s", name)

    if applied == 0:
        return False, "Стратегии пришли, но не записались (проверьте доступ)."

    cfg["pro_strategy_cloud_ver"] = version
    from . import config as appconfig
    appconfig.save(cfg)
    log.info("applied %d cloud strategies, version %s", applied, version)
    return True, f"Обновлено стратегий: {applied}."


def run_async(cfg, on_done: Callable[[str], None]) -> None:
    """Фоновый запуск с уведомлением результата в UI (через on_done).

    Сообщения об ошибках (сервер недоступен, манифест повреждён) тоже
    доходят до UI — раньше они глотались, и пользователь не видел,
    почему стратегии не обновились.
    """

    def _work() -> None:
        try:
            changed, msg = apply_cloud_strategies(cfg)
        except Exception:
            log.exception("strategy_cloud background failed")
            changed, msg = False, "Ошибка проверки облачных стратегий."
        if msg:
            try:
                on_done(msg)
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True, name="strategy-cloud").start()


def should_run(cfg) -> bool:
    """Нужно ли вообще трогать сеть на старте."""
    try:
        return (bool(cfg.get("pro_strategy_cloud_enabled", True))
                and bool(STRATEGY_MANIFEST_URL))
    except Exception:
        return False
