"""Конфигурация приложения: загрузка/сохранение, дефолты."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


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

    # general
    "autostart_with_windows": False,
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
    return cfg


def save(cfg: Dict[str, Any]) -> None:
    try:
        app_dir().mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as fp:
            json.dump(cfg, fp, indent=2, ensure_ascii=False)
    except Exception:
        pass
