"""Централизованное логирование EXDPI.

Все логи лежат в одной папке ``%APPDATA%\\EXDPI\\logs\\``:

* ``exdpi.log``  — общий лог приложения (контроллер, UI, прокси, DNS, трей);
* ``winws.log``  — весь stdout/stderr процесса winws.exe с таймстампами;
* ``*.log.1..5`` — ротация (RotatingFileHandler, 2 МБ × 5 файлов).

API:
    setup()                — настроить root-логгер + отдельный winws-логгер;
    logs_dir()             — путь к папке логов (Path);
    winws_logger()         — логгер для вывода winws.exe (пишет в winws.log);
    open_logs_folder()     — открыть папку логов в проводнике;
    tail(name, n)          — последние n строк лог-файла (для диагностики).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

from .config import app_dir

LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 МБ на файл
LOG_BACKUP_COUNT = 5

APP_LOG_NAME = "exdpi.log"
WINWS_LOG_NAME = "winws.log"

_WINWS_LOGGER_NAME = "winws"

log = logging.getLogger("dpibypass.logs")


def logs_dir() -> Path:
    """Папка с логами: %APPDATA%/EXDPI/logs (создаётся при setup/open)."""
    return app_dir() / "logs"


def app_log_path() -> Path:
    return logs_dir() / APP_LOG_NAME


def winws_log_path() -> Path:
    return logs_dir() / WINWS_LOG_NAME


def _make_handler(path: Path, fmt: str) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        str(path),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(logging.Formatter(fmt))
    return handler


def setup() -> None:
    """Настроить логирование всего приложения.

    Вызывается один раз из main.py до создания UI. Безопасно к повторному
    вызову (хендлеры не дублируются).
    """
    d = logs_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        # некуда писать — оставляем хотя бы консоль
        logging.basicConfig(level=logging.INFO)
        return

    _migrate_legacy_logs(d)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(getattr(h, "_exdpi_app_log", False) for h in root.handlers):
        try:
            handler = _make_handler(
                d / APP_LOG_NAME,
                "%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
            )
            handler._exdpi_app_log = True  # type: ignore[attr-defined]
            root.addHandler(handler)
        except Exception:
            logging.basicConfig(level=logging.INFO)

    # отдельный канал для вывода winws.exe — без пропагации в общий лог
    wl = logging.getLogger(_WINWS_LOGGER_NAME)
    wl.setLevel(logging.INFO)
    wl.propagate = False
    if not any(getattr(h, "_exdpi_winws_log", False) for h in wl.handlers):
        try:
            handler = _make_handler(d / WINWS_LOG_NAME, "%(asctime)s  %(message)s")
            handler._exdpi_winws_log = True  # type: ignore[attr-defined]
            wl.addHandler(handler)
        except Exception:
            pass

    logging.getLogger("asyncio").setLevel(logging.WARNING)


def winws_logger() -> logging.Logger:
    """Логгер, в который zapret_runner пишет вывод winws.exe построчно."""
    return logging.getLogger(_WINWS_LOGGER_NAME)


def _migrate_legacy_logs(target_dir: Path) -> None:
    """Перенести старые логи (exdpi.log, winws-stderr.log из корня app_dir)
    в новую папку logs/, чтобы у пользователя не было двух мест с логами."""
    legacy = [
        (app_dir() / "exdpi.log", target_dir / "exdpi-legacy.log"),
        (app_dir() / "winws-stderr.log", target_dir / "winws-legacy.log"),
    ]
    for src, dst in legacy:
        try:
            if src.exists() and not dst.exists():
                src.replace(dst)
        except Exception:
            # перенос не критичен
            pass


def open_logs_folder() -> bool:
    """Открыть папку логов в файловом менеджере. True при успехе."""
    d = logs_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        log.exception("failed to create logs dir")
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(d))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(d)])
        else:
            subprocess.Popen(["xdg-open", str(d)])
        return True
    except Exception:
        log.exception("failed to open logs folder")
        return False


def tail(filename: str, lines: int = 10) -> List[str]:
    """Последние ``lines`` строк лог-файла из папки логов (для диагностики)."""
    path = logs_dir() / filename
    try:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.strip().splitlines()[-lines:]
    except Exception:
        return []
