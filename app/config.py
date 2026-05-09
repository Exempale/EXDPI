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


DEFAULT: Dict[str, Any] = {
    # tg-ws-proxy
    "proxy_enabled": True,
    "proxy_port": 1443,
    "proxy_host": "127.0.0.1",
    "proxy_secret": "",
    "proxy_dc_ip": ["2:149.154.167.220", "4:149.154.167.220"],

    # zapret
    "zapret_enabled": True,
    "zapret_strategy": "general (ALT10).bat",
    "custom_domains": list(DEFAULT_CUSTOM_DOMAINS),

    # general
    "autostart_with_windows": False,
    # сворачивать в трей по крестику окна (вместо выхода)
    "minimize_to_tray": True,
    # запускать программу свёрнутой (например, при автозапуске Windows)
    "start_minimized": False,

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
    return cfg


def save(cfg: Dict[str, Any]) -> None:
    try:
        app_dir().mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as fp:
            json.dump(cfg, fp, indent=2, ensure_ascii=False)
    except Exception:
        pass
