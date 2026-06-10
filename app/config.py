"""Конфигурация приложения: загрузка/сохранение, дефолты."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


APP_DIRNAME = "EXDPI"


def app_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / APP_DIRNAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIRNAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_DIRNAME


CONFIG_FILE = app_dir() / "config.json"


def _default_secret() -> str:
    return os.urandom(16).hex()


# Дефолтный набор доменов, которые часто блокируют у российских провайдеров,
# но которых нет в стоковом list-general.txt zapret. ИИ-сайты в первую очередь.
DEFAULT_CUSTOM_DOMAINS: List[str] = [
    # OpenAI / ChatGPT
    "chatgpt.com",
    "openai.com",
    "oaistatic.com",
    "oaiusercontent.com",
    "cdn.openai.com",
    # Anthropic / Claude
    "claude.ai",
    "claude.com",
    "anthropic.com",
    # Devin
    "app.devin.ai",
    "devin.ai",
    # Perplexity
    "perplexity.ai",
    "www.perplexity.ai",
    # Google AI / Gemini
    "gemini.google.com",
    "aistudio.google.com",
    # xAI / Grok — добавлены все основные субдомены, иначе grok.com
    # часто не пускает: фронт грузится с CDN/asset-сабдоменов
    "grok.com",
    "www.grok.com",
    "x.ai",
    "www.x.ai",
    "api.x.ai",
    "accounts.x.ai",
    "assets.x.ai",
    "cdn.x.ai",
    # HuggingFace
    "huggingface.co",
    "hf.co",
    # MS Copilot
    "copilot.microsoft.com",
    # Misc
    "you.com",
    "poe.com",
    # CDN — без них браузер часто не может скачать ассеты ИИ-сайтов
    # (app.devin.ai → CloudFront, grok.com → Cloudflare и т.п.)
    "cloudfront.net",
    "cloudflare.com",
    "cdn.cloudflare.net",
    "r2.cloudflarestorage.com",
]


_DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)+$")


def normalize_domain(raw: str) -> str:
    """Привести строку к нормальному hostname или вернуть пустую строку."""
    if raw is None:
        return ""
    d = str(raw).strip().lower()
    if not d:
        return ""
    # отбросить scheme
    for sch in ("https://", "http://", "wss://", "ws://", "tg://"):
        if d.startswith(sch):
            d = d[len(sch):]
            break
    # отбросить путь / порт / query / фрагмент
    for sep in ("/", "?", "#"):
        if sep in d:
            d = d.split(sep, 1)[0]
    if ":" in d:
        d = d.split(":", 1)[0]
    while d.startswith("."):
        d = d[1:]
    if d.endswith("."):
        d = d[:-1]
    if not d or " " in d or "\t" in d:
        return ""
    if not _DOMAIN_RE.match(d):
        return ""
    return d


def parse_domains(raw: str) -> List[str]:
    """Распарсить пользовательский ввод (мультистрока с ; , whitespace разделителями)."""
    if not raw:
        return []
    parts = re.split(r"[;,\s]+", raw)
    out: List[str] = []
    seen: set = set()
    for p in parts:
        n = normalize_domain(p)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def normalize_domain_list(items: Iterable[Any]) -> List[str]:
    """Нормализовать готовый список (например, после загрузки конфига)."""
    out: List[str] = []
    seen: set = set()
    for it in items or []:
        n = normalize_domain(it)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


# Допустимые значения для game_mode:
#   "normal"       — обычный режим (GameFilter=12, как при выключенном фильтре
#                    в оригинальном service.bat — обрабатываются только
#                    стандартные TLS/HTTP/QUIC порты);
#   "gaming"       — игровой режим (GameFilter=1024-65535 для TCP+UDP, ловим
#                    высокие порты — Discord-голос, игровые лобби, P2P).
GAME_MODES = ("normal", "gaming")

GAME_FILTER_PORTS = {
    "normal": "12",
    "gaming": "1024-65535",
}


DEFAULT: Dict[str, Any] = {
    # tg-ws-proxy
    "proxy_enabled": True,
    "proxy_port": 1443,
    "proxy_host": "127.0.0.1",
    "proxy_secret": "",
    "proxy_dc_ip": ["2:149.154.167.220", "4:149.154.167.220"],

    # zapret
    "zapret_enabled": True,
    # имя general*.bat либо спец-значение "auto" (см. strategy_auto.py)
    "zapret_strategy": "general (ALT10).bat",
    # результат последнего авто-подбора стратегии (имя .bat) — используется,
    # когда zapret_strategy == "auto"
    "zapret_strategy_auto_result": "",
    # «Свои домены» по умолчанию пустые — пользователь сам наполняет список,
    # либо переключается на один из готовых пресетов (см. domain_preset).
    "custom_domains": [],
    # пресет «готовых доменов» — последний выбранный preset из blocklists/.
    # При смене preset-а в UI его содержимое попадает в custom_domains.
    "domain_preset": "custom",
    # режим работы zapret: обычный или игровой (см. GAME_MODES выше).
    "game_mode": "normal",

    # защищённый DNS (DoH/DoT) — см. app/securedns.py
    "securedns_enabled": False,
    # протокол: "doh" (DNS-over-HTTPS) или "dot" (DNS-over-TLS)
    "securedns_protocol": "doh",
    # провайдер: cloudflare / google / quad9 / adguard
    "securedns_provider": "cloudflare",
    # прописывать 127.0.0.1 системным DNS при включении (с бэкапом и
    # восстановлением прежних настроек при выключении)
    "securedns_set_system": True,

    # general
    "autostart_with_windows": False,
    # сворачивать в трей по крестику окна (вместо выхода)
    "minimize_to_tray": True,
    # запускать программу свёрнутой (например, при автозапуске Windows)
    "start_minimized": False,
    # тема оформления интерфейса (см. app/theme.py: dark / light)
    "theme": "dark",
    # уведомления Windows (вкл/выкл обхода, ошибки, обновления)
    "notifications_enabled": True,
    # пройден ли анимированный мастер первого запуска (app/ui_wizard.py)
    "wizard_done": False,

    # авто-проверка обновлений: timestamp (sec since epoch), до которого
    # не показывать диалог (после клика «пропустить обновление» = +3 дня)
    "update_skip_until": 0,
}


def load() -> Dict[str, Any]:
    cfg: Dict[str, Any] = dict(DEFAULT)
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, dict):
                    cfg.update(data)
    except Exception:
        pass
    if not cfg.get("proxy_secret"):
        cfg["proxy_secret"] = _default_secret()
    cfg["custom_domains"] = normalize_domain_list(cfg.get("custom_domains") or [])
    if cfg.get("game_mode") not in GAME_MODES:
        cfg["game_mode"] = "normal"
    if not isinstance(cfg.get("theme"), str) or cfg["theme"] not in ("dark", "light"):
        cfg["theme"] = "dark"
    if cfg.get("securedns_protocol") not in ("doh", "dot"):
        cfg["securedns_protocol"] = "doh"
    if not isinstance(cfg.get("securedns_provider"), str) or not cfg["securedns_provider"]:
        cfg["securedns_provider"] = "cloudflare"
    for bool_key in ("securedns_enabled", "securedns_set_system",
                     "notifications_enabled", "wizard_done"):
        if not isinstance(cfg.get(bool_key), bool):
            cfg[bool_key] = bool(DEFAULT[bool_key])
    if not isinstance(cfg.get("zapret_strategy_auto_result"), str):
        cfg["zapret_strategy_auto_result"] = ""
    return cfg


def save(cfg: Dict[str, Any]) -> None:
    try:
        app_dir().mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as fp:
            json.dump(cfg, fp, indent=2, ensure_ascii=False)
    except Exception:
        pass
