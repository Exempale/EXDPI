"""DPI-обход на Linux: nfqws (zapret, bol-van) + iptables NFQUEUE.

Движок nfqws собирается в CI из исходников zapret и кладётся в
``resources/zapret-linux/nfqws``. Стратегии — те же general*.bat, что и на
Windows: их аргументы почти полностью совместимы с nfqws (движок один),
выбрасываются только виндовые флаги (--wf-tcp/--wf-udp/--ip-id).

Файрвол: iptables mangle NFQUEUE (queue 200). Правила помечены
``--queue-bypass`` — если nfqws умер, пакеты идут напрямую, интернет не
падает. nfqws помечает свои пакеты (--set-mark 0x40000000), чтобы не
зациклиться.

Требуется root (TUN не нужен, но NFQUEUE и iptables — admin-привилегии):
EXDPI на Linux запускается через sudo.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

log = logging.getLogger("dpibypass.zapret.linux")

QUEUE_NUM = 200
MARK = "0x40000000"


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _res() -> Path:
    from . import paths
    return paths.resource_root() / "zapret-linux"


def list_strategies() -> List[str]:
    d = _res() / "strategies"
    if not d.exists():
        return ["general.bat"]
    items = sorted(p.name for p in d.glob("general*.bat"))
    return items or ["general.bat"]


def _sh(cmd: List[str], timeout: float = 15.0) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        log.warning("command failed %s: %s", cmd[:3], exc)
        return None


def _default_iface() -> str:
    out = _sh(["ip", "route", "show", "default"])
    if out and out.stdout:
        parts = out.stdout.split()
        if "dev" in parts:
            return parts[parts.index("dev") + 1]
    return ""


def _ports_from_args(args: List[str], flag: str, default: str) -> str:
    """Собрать набор портов из --filter-tcp/--filter-udp значений стратегии."""
    ports: List[str] = []
    for a in args:
        if a.startswith(flag + "="):
            ports.extend(a.split("=", 1)[1].split(","))
    return ",".join(p for p in ports if p) or default


class NfqwsRunner:
    """Тот же интерфейс, что и ZapretRunner на Windows."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._strategy: Optional[str] = None
        self.intentional_stop = False
        self._applied_rules: List[List[str]] = []

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def strategy(self) -> Optional[str]:
        return self._strategy

    # ── стратегии ────────────────────────────────────────────────────
    def _strategy_args(self, bat_name: str, game_mode: str) -> List[str]:
        res = _res()
        bat = res / "strategies" / bat_name
        if not bat.exists():
            raise FileNotFoundError(f"Стратегия не найдена: {bat_name}")
        text = bat.read_text(encoding="utf-8", errors="replace")
        # тот же регекс, что и в Windows-парсере: start "..." /min "%BIN%winws.exe" ...
        from .zapret_runner import _START_RE
        m = _START_RE.search(text)
        if not m:
            raise RuntimeError(f"Не удалось распарсить стратегию: {bat_name}")
        args_text = m.group("args")
        args_text = re.sub(r"\^\s*\r?\n", " ", args_text)
        args_text = args_text.split("\n", 1)[0]

        bin_dir = str(res / "bin") + "/"
        lists_dir = str(res / "lists") + "/"
        args_text = args_text.replace("%BIN%", bin_dir).replace("%LISTS%", lists_dir)
        # виндовые разделители путей в .bat → POSIX
        args_text = args_text.replace("\\", "/")

        game_ports = "1024-65535" if game_mode == "gaming" else "12"
        args_text = args_text.replace("%GameFilterTCP%", game_ports)
        args_text = args_text.replace("%GameFilterUDP%", game_ports)
        args_text = args_text.replace("%GameFilter%", game_ports)

        args = [a.strip() for a in shlex.split(args_text, posix=True) if a.strip()]
        # виндовые флаги, которых нет у nfqws
        drop = ("--wf-tcp", "--wf-udp", "--wf-raw-part", "--ip-id")
        args = [a for a in args if not a.startswith(drop)]
        log.debug("nfqws args: %s", args)
        return args

    # ── файрвол ──────────────────────────────────────────────────────
    def _apply_rules(self, iface: str, args: List[str]) -> None:
        tcp = _ports_from_args(args, "--filter-tcp", "80,443")
        udp = _ports_from_args(args, "--filter-udp", "443")
        base = ["iptables", "-t", "mangle", "-I", "POSTROUTING", "-o", iface]
        rules = [
            base + ["-p", "tcp", "-m", "multiport", "--dports", tcp,
                    "-m", "connbytes", "--connbytes-dir=original",
                    "--connbytes-mode=packets", "--connbytes", "1:4",
                    "-m", "mark", "!", "--mark", f"{MARK}/{MARK}",
                    "-j", "NFQUEUE", "--queue-num", str(QUEUE_NUM),
                    "--queue-bypass"],
            base + ["-p", "udp", "-m", "multiport", "--dports", udp,
                    "-m", "mark", "!", "--mark", f"{MARK}/{MARK}",
                    "-j", "NFQUEUE", "--queue-num", str(QUEUE_NUM),
                    "--queue-bypass"],
        ]
        for rule in rules:
            if _sh(rule):
                self._applied_rules.append(rule)
                log.info("iptables: %s", " ".join(rule[3:]))

    def _remove_rules(self) -> None:
        for rule in reversed(self._applied_rules):
            _sh(["iptables", "-t", "mangle", "-D"] + rule[6:])
        self._applied_rules = []

    # ── lifecycle ────────────────────────────────────────────────────
    def start(
        self,
        strategy: str,
        on_exit: Optional[Callable[[int], None]] = None,
        custom_domains: Optional[List[str]] = None,
        game_mode: str = "normal",
    ) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if not is_root():
            raise RuntimeError(
                "Linux: для DPI-обхода нужны права root — запустите EXDPI через sudo")
        nfqws = _res() / "nfqws"
        if not nfqws.exists():
            raise RuntimeError("Движок nfqws не найден в этой сборке")

        lists = _res() / "lists"
        lists.mkdir(parents=True, exist_ok=True)
        if custom_domains is not None:
            (lists / "list-general-user.txt").write_text(
                "\n".join(custom_domains), encoding="utf-8")

        args = self._strategy_args(strategy, game_mode)
        iface = _default_iface()
        if not iface:
            raise RuntimeError("Не удалось определить сетевой интерфейс")
        self._remove_rules()
        self._apply_rules(iface, args)

        self.intentional_stop = False
        cmd = [str(nfqws), f"--qnum={QUEUE_NUM}", f"--set-mark={MARK}", *args]
        log.info("zapret start: %s (game_mode=%s, iface=%s)",
                 strategy, game_mode, iface)
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception as exc:
            log.error("nfqws launch failed: %s", exc)
            self._remove_rules()
            raise
        self._strategy = strategy
        if on_exit:
            threading.Thread(target=self._wait, args=(on_exit,),
                             daemon=True, name="nfqws-wait").start()

    def _wait(self, on_exit: Callable[[int], None]) -> None:
        assert self._proc is not None
        rc = self._proc.wait()
        if getattr(self, "intentional_stop", False):
            self.intentional_stop = False
            log.info("zapret stopped intentionally (rc=%s)", rc)
            return
        log.info("nfqws exited rc=%s", rc)
        try:
            on_exit(rc)
        except Exception:
            pass

    def stop(self, timeout: float = 4.0) -> None:
        proc, self._proc = self._proc, None
        self._strategy = None
        self._remove_rules()
        if not proc or proc.poll() is not None:
            return
        log.info("zapret stop")
        self.intentional_stop = True
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
