"""Запуск zapret (winws.exe) с парсингом стратегии из .bat-файла."""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys
import threading
from typing import Callable, List, Optional

from . import paths

log = logging.getLogger("dpibypass.zapret")


def _kill_orphan_winws() -> int:
    """Убить чужие/осиротевшие winws.exe перед запуском нашего.

    winws.exe ставит WinDivert-фильтр на сетевом уровне. Два процесса
    одновременно с одинаковым фильтром = моментальный rc=1 ("filter handle
    in use"). Прошлый процесс (например, после краша или нескольких запусков
    EXDPI подряд) держит фильтр и не даёт стартовать новому.
    """
    if sys.platform != "win32":
        return 0
    killed = 0
    try:
        CREATE_NO_WINDOW = 0x08000000
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "winws.exe"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
        if result.returncode == 0:
            out = result.stdout.decode("cp866", errors="replace")
            killed = out.count("PID")
            log.info("killed orphan winws.exe (%d)", killed)
    except Exception:
        log.exception("kill orphan winws failed")
    return killed


_START_RE = re.compile(
    r'start\s+"[^"]*"\s+/min\s+"%BIN%winws\.exe"\s+(?P<args>.*?)(?=^\s*(?:@|echo|cd|set|goto|:[A-Za-z]|\Z))',
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


def open_service_bat() -> bool:
    """Запустить service.bat (диспетчер/меню оригинального zapret).

    Используется кнопкой в разделе «Для разработчиков». service.bat сам
    запрашивает права администратора (через powershell RunAs), поэтому просто
    открываем его в новом окне консоли. Возвращает True при успешном запуске.
    """
    bat = paths.service_bat()
    if not bat.exists():
        log.warning("service.bat не найден: %s", bat)
        return False
    try:
        if sys.platform == "win32":
            # cmd /c start "" "<bat>" — откроет .bat в собственном окне консоли,
            # дальше service.bat сам поднимет UAC и покажет своё меню.
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(bat)],
                cwd=str(bat.parent),
                creationflags=CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
            )
        else:
            # вне Windows .bat не выполнить — просто открываем файл на просмотр.
            subprocess.Popen(["xdg-open", str(bat)])
        log.info("service.bat запущен: %s", bat)
        return True
    except Exception:
        log.exception("не удалось запустить service.bat")
        return False


def list_strategies() -> List[str]:
    """Все доступные стратегии (general*.bat)."""
    root = paths.zapret_root()
    if not root.is_dir():
        return ["general.bat"]
    items = sorted(p.name for p in root.glob("general*.bat"))
    return items or ["general.bat"]


def parse_strategy(bat_name: str, game_mode: str = "normal") -> List[str]:
    """Извлечь аргументы winws.exe из .bat-стратегии.

    Подставляет %BIN% / %LISTS% / GameFilter*. Возвращает уже готовый
    argv-список без самого winws.exe.

    ``game_mode``:
        * "normal" — GameFilter=12 (как при выключенном фильтре в оригинальном
          service.bat — обрабатываются только стандартные TLS/HTTP/QUIC порты);
        * "gaming" — GameFilter=1024-65535 для TCP+UDP (Discord-голос,
          игровые лобби, P2P-трафик), как в режиме "all" service.bat.
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

    # Game filter — высокие порты (1024-65535) для гейминг-режима, "12" для
    # обычного. "12" — это спецзначение из service.bat, означающее «ничего
    # не подставлять» и эквивалент выключенного фильтра.
    game_ports = "1024-65535" if game_mode == "gaming" else "12"
    args_text = args_text.replace("%GameFilterTCP%", game_ports)
    args_text = args_text.replace("%GameFilterUDP%", game_ports)
    args_text = args_text.replace("%GameFilter%", game_ports)

    # posix=True корректно разбирает кавычки внутри аргументов вида
    # --hostlist="/path/file.txt"
    args = shlex.split(args_text, posix=True)
    args = [a.strip() for a in args if a.strip()]

    # ── фикс Roblox в гейминг-режиме ────────────────────────────────
    # Roblox держит игровое соединение по UDP на высоких портах
    # (49152-65535, RakNet/ENet). В стоковых стратегиях единственная секция
    # для этих портов фильтруется по ipset-all.txt, который у нас пустой
    # (плейсхолдер) — поэтому игровой UDP-трафик Roblox не десинхронизируется
    # и DPI его режет: сайт открывается, а в игру зайти нельзя.
    # Добавляем отдельный профиль для игрового UDP БЕЗ привязки к ipset,
    # чтобы фейки уходили на любые сервера Roblox. Только в гейминг-режиме —
    # в обычном высокие порты не дивертятся (--wf-udp их не ловит).
    if game_mode == "gaming":
        args.extend(_roblox_udp_fix_args())

    return args


def _roblox_udp_fix_args() -> List[str]:
    """Доп. winws-профиль для игрового UDP Roblox (см. parse_strategy).

    Десинхронизирует первые пакеты UDP-флоу на портах 49152-65535 без
    ipset-привязки. cutoff=n2 — фейки только на старте соединения, дальше
    трафик идёт без вмешательства (минимум влияния на пинг).
    """
    bin_dir = paths.zapret_bin()
    fake_udp = bin_dir / "quic_initial_dbankcloud_ru.bin"
    return [
        "--new",
        "--filter-udp=49152-65535",
        "--dpi-desync=fake",
        "--dpi-desync-any-protocol=1",
        f"--dpi-desync-fake-unknown-udp={fake_udp}",
        "--dpi-desync-repeats=8",
        "--dpi-desync-cutoff=n2",
    ]


_USER_LISTS_DEFAULTS = {
    "ipset-exclude-user.txt": "203.0.113.113/32\n",
    "list-general-user.txt": "domain.example.abc\n",
    "list-exclude-user.txt": "domain.example.abc\n",
}

USER_HOSTLIST_FILE = "list-general-user.txt"


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


def write_user_hostlist(domains: List[str]) -> int:
    """Перезаписать list-general-user.txt пользовательскими доменами.

    Возвращает количество доменов, фактически записанных в файл (без плейсхолдера).
    Если список пуст — пишем плейсхолдер, чтобы winws.exe не падал rc=1 на
    пустом --hostlist=...
    """
    lists_dir = paths.zapret_lists()
    try:
        lists_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log.warning("failed to mkdir lists dir: %s", lists_dir)
        return 0

    valid: List[str] = []
    seen: set = set()
    for raw in domains or []:
        d = (raw or "").strip().lower()
        if not d or " " in d or "\t" in d:
            continue
        if "." not in d:
            continue
        if d in seen:
            continue
        seen.add(d)
        valid.append(d)

    path = lists_dir / USER_HOSTLIST_FILE
    body = "\n".join(valid) if valid else "domain.example.abc"
    try:
        path.write_text(body + "\n", encoding="utf-8")
    except Exception as exc:
        log.warning("failed to write user hostlist: %s", exc)
        return 0
    return len(valid)


class ZapretRunner:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._strategy: Optional[str] = None
        # последние строки вывода winws.exe — для диагностики rc != 0
        self._out_tail: List[str] = []
        self._tail_lock = threading.Lock()

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
        custom_domains: Optional[List[str]] = None,
        game_mode: str = "normal",
    ) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return

            # убиваем осиротевшие winws.exe от предыдущих запусков —
            # иначе WinDivert-фильтр занят и наш winws.exe моментально rc=1.
            _kill_orphan_winws()

            ensure_user_lists()
            if custom_domains is not None:
                n = write_user_hostlist(custom_domains)
                log.info("user hostlist: %d domains", n)
            log.info("zapret game_mode=%s", game_mode)
            args = parse_strategy(strategy, game_mode=game_mode)
            winws = paths.zapret_bin() / "winws.exe"
            if not winws.exists():
                raise RuntimeError(f"winws.exe не найден: {winws}")

            cmd = [str(winws), *args]
            log.info("zapret start: %s (game_mode=%s)", strategy, game_mode)
            log.debug("argv: %s", cmd)

            # stdout+stderr winws.exe идут в logs/winws.log через reader-поток
            # (см. _pump_output) — без этого rc=1 диагностировать невозможно.
            kw: dict = dict(
                cwd=str(paths.zapret_bin()),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
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

            with self._tail_lock:
                self._out_tail = []
            threading.Thread(
                target=self._pump_output,
                args=(self._proc,),
                daemon=True,
                name="winws-log",
            ).start()

            self._strategy = strategy

        if on_exit:
            threading.Thread(
                target=self._wait, args=(on_exit,), daemon=True, name="zapret-wait",
            ).start()

    def _pump_output(self, proc: subprocess.Popen) -> None:
        """Читает stdout/stderr winws.exe построчно и пишет в logs/winws.log.

        Хвост вывода (последние строки) дополнительно копится в памяти,
        чтобы при rc != 0 показать его в общем логе без чтения файла.
        """
        try:
            from .logs import winws_logger
            wlog = winws_logger()
        except Exception:
            wlog = log

        stream = proc.stdout
        if stream is None:
            return
        wlog.info("─── winws.exe session start (pid=%s) ───", proc.pid)
        try:
            for raw in iter(stream.readline, b""):
                line = ""
                for enc in ("utf-8", "cp866", "cp1251"):
                    try:
                        line = raw.decode(enc).rstrip("\r\n")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line.strip():
                    continue
                wlog.info("%s", line)
                with self._tail_lock:
                    self._out_tail.append(line)
                    if len(self._out_tail) > 40:
                        self._out_tail = self._out_tail[-40:]
        except Exception:
            log.exception("winws output pump failed")
        finally:
            try:
                stream.close()
            except Exception:
                pass
            wlog.info("─── winws.exe session end ───")

    def last_output_tail(self, lines: int = 10) -> List[str]:
        """Последние строки вывода winws.exe текущей/прошлой сессии."""
        with self._tail_lock:
            return list(self._out_tail[-lines:])

    def _wait(self, on_exit: Callable[[int], None]) -> None:
        try:
            rc = self._proc.wait() if self._proc else 0  # type: ignore[union-attr]
        except Exception:
            rc = -1
        if rc != 0:
            tail = self.last_output_tail(10)
            if tail:
                log.error("winws.exe output (last %d lines):", len(tail))
                for line in tail:
                    log.error("  %s", line)
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

        # на всякий случай добиваем любые осиротевшие winws.exe — иначе
        # следующий start() снова словит rc=1 из-за занятого фильтра.
        _kill_orphan_winws()
