"""Запуск zapret (winws.exe) с парсингом стратегии из .bat-файла."""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, List, Optional

from . import paths

log = logging.getLogger("dpibypass.zapret")


_START_RE = re.compile(
    r'start\s+"[^"]*"\s+/min\s+"%BIN%winws\.exe"\s+(?P<args>.*?)(?=^\s*(?:@|echo|cd|set|goto|:[A-Za-z]|\Z))',
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


def list_strategies() -> List[str]:
    """Все доступные стратегии (general*.bat)."""
    root = paths.zapret_root()
    if not root.is_dir():
        return ["general.bat"]
    items = sorted(p.name for p in root.glob("general*.bat"))
    return items or ["general.bat"]


def parse_strategy(bat_name: str) -> List[str]:
    """Извлечь аргументы winws.exe из .bat-стратегии.

    Подставляет %BIN% / %LISTS% / GameFilter*. Возвращает уже готовый
    argv-список без самого winws.exe.
    """
    bat_path = paths.zapret_root() / bat_name
    if not bat_path.exists():
        raise FileNotFoundError(f"Стратегия не найдена: {bat_name}")

    text = bat_path.read_text(encoding="utf-8", errors="replace")

    m = _START_RE.search(text)
    if not m:
        raise RuntimeError(f"Не удалось распарсить стратегию: {bat_name}")

    args_text = m.group("args")
    # склейка переносов вида `^\r?\n`
    args_text = re.sub(r"\^\s*\r?\n", " ", args_text)
    # отбрасываем хвост на новой строке (после некомандного контента)
    args_text = args_text.split("\n", 1)[0]

    bin_dir = str(paths.zapret_bin()) + os.sep
    lists_dir = str(paths.zapret_lists()) + os.sep
    args_text = args_text.replace("%BIN%", bin_dir).replace("%LISTS%", lists_dir)
    # фильтр игр выключён по умолчанию (как в service.bat при отсутствии
    # utils\game_filter.enabled). Подставляем "12" — этот же дефолт.
    args_text = args_text.replace("%GameFilterTCP%", "12")
    args_text = args_text.replace("%GameFilterUDP%", "12")
    args_text = args_text.replace("%GameFilter%", "12")

    # posix=True корректно разбирает кавычки внутри аргументов вида
    # --hostlist="/path/file.txt"
    args = shlex.split(args_text, posix=True)
    args = [a.strip() for a in args if a.strip()]
    return args


_USER_LISTS_DEFAULTS = {
    "ipset-exclude-user.txt": "203.0.113.113/32\n",
    "list-general-user.txt": "domain.example.abc\n",
    "list-exclude-user.txt": "domain.example.abc\n",
}


def ensure_user_lists() -> None:
    """Создаёт плейсхолдеры для *-user.txt файлов, которые использует general*.bat.

    Оригинальный zapret создаёт их в service.bat :load_user_lists перед запуском
    winws.exe; без этих файлов winws.exe валится rc=1 на --hostlist=/.../...-user.txt.

    В onefile-режиме PyInstaller resources/ экстрактит в _MEIPASS, куда можно
    писать во время работы процесса.
    """
    lists_dir = paths.zapret_lists()
    try:
        lists_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    for fname, default in _USER_LISTS_DEFAULTS.items():
        path = lists_dir / fname
        if path.exists():
            continue
        try:
            path.write_text(default, encoding="utf-8")
        except Exception:
            log.warning("failed to seed %s", path)


class ZapretRunner:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._strategy: Optional[str] = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    @property
    def strategy(self) -> Optional[str]:
        return self._strategy

    def start(
        self,
        strategy: str,
        on_exit: Optional[Callable[[int], None]] = None,
    ) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return

            ensure_user_lists()
            args = parse_strategy(strategy)
            winws = paths.zapret_bin() / "winws.exe"
            if not winws.exists():
                raise RuntimeError(f"winws.exe не найден: {winws}")

            cmd = [str(winws), *args]
            log.info("zapret start: %s", strategy)
            log.debug("argv: %s", cmd)

            kw: dict = dict(
                cwd=str(paths.zapret_bin()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            if sys.platform == "win32":
                CREATE_NO_WINDOW = 0x08000000
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                kw["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP

            try:
                self._proc = subprocess.Popen(cmd, **kw)
            except Exception as exc:
                log.error("zapret launch failed: %s", exc)
                raise

            self._strategy = strategy

        if on_exit:
            threading.Thread(
                target=self._wait, args=(on_exit,), daemon=True, name="zapret-wait",
            ).start()

    def _wait(self, on_exit: Callable[[int], None]) -> None:
        try:
            rc = self._proc.wait() if self._proc else 0  # type: ignore[union-attr]
        except Exception:
            rc = -1
        try:
            on_exit(rc)
        except Exception:
            pass

    def stop(self, timeout: float = 4.0) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            self._strategy = None

        if not proc or proc.poll() is not None:
            return

        log.info("zapret stop")
        try:
            proc.terminate()
        except Exception:
            pass

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
        except Exception:
            pass
