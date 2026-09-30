"""DPI-обход на macOS: движок utunws (ZapretMac, Flowseal, MIT) + LaunchDaemon.

В бандл приложения входит Payload порта ZapretMac (bin/utunws, стратегии
*.conf.in, default-lists). EXDPI устанавливает его в
``/Library/Application Support/EXDPI/zapret`` и управляет собственным
LaunchDaemon ``io.github.exdpi.zapret`` (скрипты exdpi-*.sh — адаптация
run.sh/stop.sh/install.sh ZapretMac под пути EXDPI).

Состояние пользователя: ``~/Library/Application Support/EXDPI`` — файл
selected-strategy, ipset-mode и lists/ (включая list-general-user.txt из
настроек EXDPI). Требуется root: EXDPI на macOS запускается через sudo.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

log = logging.getLogger("dpibypass.zapret.mac")

LABEL = "io.github.exdpi.zapret"
ENGINE_DIR = Path("/Library/Application Support/EXDPI/zapret")
PLIST = Path("/Library/LaunchDaemons") / f"{LABEL}.plist"


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _res() -> Path:
    from . import paths
    return paths.resource_root() / "zapret-mac"


def _data_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "EXDPI"


def _sh(cmd: List[str], timeout: float = 60.0) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        log.warning("command failed %s: %s", cmd[:3], exc)
        return None


def display_to_conf(bat_name: str) -> str:
    """'general (ALT2).bat' → 'general-alt2' (имя .conf.in движка)."""
    base = re.sub(r"\.bat$", "", str(bat_name), flags=re.I).strip()
    m = re.match(r"^general\s*\((.+)\)$", base, flags=re.I)
    if not m:
        return "general"
    words = re.findall(r"[A-Za-z0-9]+", m.group(1))
    return "general-" + "-".join(w.lower() for w in words)


def conf_to_display(conf: str) -> str:
    """'general-alt2' → 'general (ALT2).bat' (обратно, для UI)."""
    m = re.match(r"^general(-[a-z0-9]+)*$", conf)
    if not m or conf == "general":
        return "general.bat"
    tail = conf[len("general-"):]
    return "general (" + tail.upper() + ").bat"


def list_strategies() -> List[str]:
    d = _res() / "strategies"
    if not d.exists():
        return ["general.bat"]
    names = sorted(p.stem for p in d.glob("general*.conf.in"))
    out = [conf_to_display(n) for n in names]
    return out or ["general.bat"]


def _is_running_daemon() -> bool:
    r = _sh(["pgrep", "-x", "utunws"], timeout=10)
    return bool(r and r.returncode == 0)


class MacRunner:
    """Тот же интерфейс, что и ZapretRunner на Windows."""

    def __init__(self) -> None:
        self._strategy: Optional[str] = None
        self.intentional_stop = False
        self._was_running = False

    @property
    def is_running(self) -> bool:
        return _is_running_daemon()

    @property
    def strategy(self) -> Optional[str]:
        return self._strategy

    # ── установка движка ─────────────────────────────────────────────
    def _install(self) -> None:
        src = _res()
        for need in ("bin/utunws", "strategies", "default-lists", "watchdog.sh",
                     "exdpi-install.sh", "exdpi-run.sh", "exdpi-stop.sh",
                     "exdpi-plist.xml.in"):
            if not (src / need).exists():
                raise RuntimeError(f"Движок zapret-mac неполный: нет {need}")
        data_root = _data_root()
        r = _sh(["/bin/sh", str(src / "exdpi-install.sh"), str(src), str(data_root)],
                timeout=120)
        if r is None or r.returncode != 0:
            tail = (r.stderr or r.stdout or "")[-400:] if r else "timeout"
            raise RuntimeError(f"Не удалось установить zapret-движок: {tail}")

    # ── lifecycle ────────────────────────────────────────────────────
    def start(
        self,
        strategy: str,
        on_exit: Optional[Callable[[int], None]] = None,
        custom_domains: Optional[List[str]] = None,
        game_mode: str = "normal",
    ) -> None:
        if _is_running_daemon():
            self.stop()
        if not is_root():
            raise RuntimeError(
                "macOS: для DPI-обхода нужны права root — запустите EXDPI через sudo")
        self._install()

        data_root = _data_root()
        lists = data_root / "lists"
        lists.mkdir(parents=True, exist_ok=True)
        # списки по умолчанию движка — как исходные, пользовательский не затираем
        for src in (_res() / "default-lists").glob("*.txt"):
            dst = lists / src.name
            if not dst.exists():
                shutil.copyfile(src, dst)
        if custom_domains is not None:
            (lists / "list-general-user.txt").write_text(
                "\n".join(custom_domains), encoding="utf-8")
        (data_root / "ipset-mode").write_text("none", encoding="utf-8")

        conf = display_to_conf(strategy)
        if not (_res() / "strategies" / f"{conf}.conf.in").exists():
            log.warning("нет конфига движка для %s, использую simple-fake", strategy)
            conf = "general-simple-fake"
        (data_root / "selected-strategy").write_text(conf, encoding="utf-8")
        self._strategy = strategy
        self.intentional_stop = False

        # перечитать выбранную стратегию и поднять движок
        _sh(["/bin/launchctl", "bootout", f"system/{LABEL}"], timeout=30)
        r = _sh(["/bin/launchctl", "kickstart", "-k", f"system/{LABEL}"], timeout=60)
        if r is None or r.returncode != 0:
            tail = (r.stderr or r.stdout or "")[-400:] if r else "timeout"
            raise RuntimeError(f"launchctl kickstart не сработал: {tail}")

        # ждём подъёма utun50 (как их install.sh)
        deadline = time.time() + 15
        while time.time() < deadline:
            if _sh(["/sbin/ifconfig", "utun50"], timeout=10) and \
               _sh(["/sbin/ifconfig", "utun50"], timeout=10).returncode == 0:
                break
            if not _is_running_daemon():
                break
            time.sleep(0.3)
        log.info("zapret start: %s (conf=%s)", strategy, conf)
        if on_exit:
            threading.Thread(target=self._wait, args=(on_exit,),
                             daemon=True, name="zapret-mac-wait").start()

    def _wait(self, on_exit: Callable[[int], None]) -> None:
        # движок живёт в launchd как root-демон: следим через pgrep
        was_up = False
        while not self.intentional_stop:
            up = _is_running_daemon()
            if up:
                was_up = True
            elif was_up:
                log.info("utunws исчез (launchd перезапустит или обход остановлен)")
                if not self.intentional_stop:
                    try:
                        on_exit(1)
                    except Exception:
                        pass
                return
            time.sleep(2)

    def stop(self, timeout: float = 30.0) -> None:
        self._strategy = None
        self.intentional_stop = True
        src = _res() / "exdpi-stop.sh"
        if src.exists():
            _sh(["/bin/sh", str(src)], timeout=timeout)
        else:
            _sh(["/bin/launchctl", "bootout", f"system/{LABEL}"], timeout=timeout)
        log.info("zapret stop")
