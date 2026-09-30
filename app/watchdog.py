"""Самовосстановление: watchdog следит за ядрами и поднимает их.

Что проверяется (раз в 5 секунд, только когда обход включён и Pro активна):
  * VPN-режим  — живой ли процесс sing-box;
  * DPI-режим  — живые ли winws.exe (zapret) и tg-ws-proxy.

Если процесс упал — через Controller выполняем stop → start (restart_with_new_config)
и шлём Windows-уведомление. Есть защита от «петли смерти»: если за 2 минуты было
3+ рестарта — на 2 минуты отключаемся, чтобы не дёргать систему.

Неактивно, если: нет Pro-лицензии, выключена настройка pro_selfheal_enabled
или обход выключен пользователем.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import List

from . import notify

log = logging.getLogger("dpibypass.watchdog")

_CHECK_INTERVAL = 5.0      # сек между проверками
_RESTART_WINDOW = 120.0    # сек, «откат» истории рестартов
_MAX_RESTARTS = 3          # максимум рестартов за окно, дальше — пауза
_BACKOFF = 120.0           # пауза после превышения


class Watchdog:
    def __init__(self, ctl) -> None:
        self.ctl = ctl
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._restart_times: List[float] = []
        self._backoff_until = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="pro-watchdog")
        self._thread.start()
        log.info("watchdog started")

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    # ── внутреннее ───────────────────────────────────────────────────
    def _should_run(self) -> bool:
        try:
            return bool(self.ctl.cfg.get("pro_selfheal_enabled", True))
        except Exception:
            return False

    def _loop(self) -> None:
        while not self._stop.wait(_CHECK_INTERVAL):
            try:
                if not self._should_run():
                    continue
                # гейт по намерению (target_on), а не по is_on(): is_on()
                # False как раз тогда, когда процесс упал, — и watchdog
                # никогда бы не сработал
                if not self.ctl.is_target_on():
                    self._backoff_until = 0.0
                    continue
                # автопереключение стратегий само рестартит zapret —
                # watchdog в это время не должен лезть со своими рестартами
                if getattr(self.ctl, "suppress_watchdog", False):
                    continue
                self._check()
            except Exception:
                log.exception("watchdog tick failed")

    def _check(self) -> None:
        now = time.time()
        if now < self._backoff_until:
            return

        down: List[str] = []
        try:
            if self.ctl.is_vpn:
                if not self.ctl.singbox.is_running:
                    down.append("sing-box")
            else:
                cfg = self.ctl.cfg
                if cfg.get("zapret_enabled", True) and not self.ctl.zapret.is_running:
                    down.append("zapret")
                if cfg.get("proxy_enabled", True) and not self.ctl.proxy.is_running:
                    down.append("tg-прокси")
                if cfg.get("securedns_enabled", False) and not self.ctl.securedns.is_running:
                    down.append("защищённый DNS")
        except Exception as exc:
            log.debug("watchdog probe failed: %s", exc)
            return

        if not down:
            return

        self._restart_times = [t for t in self._restart_times if now - t < _RESTART_WINDOW]
        if len(self._restart_times) >= _MAX_RESTARTS:
            self._backoff_until = now + _BACKOFF
            log.warning("watchdog: too many restarts, backing off %ds", _BACKOFF)
            try:
                notify.send("Самовосстановление: слишком много сбоев, "
                            "делаю паузу. Проверьте логи.")
            except Exception:
                pass
            return

        self._restart_times.append(now)
        log.warning("watchdog restarting: %s", ", ".join(down))
        try:
            self.ctl.restart_with_new_config()
            try:
                notify.send("Самовосстановление: поднял упавшее — "
                            + ", ".join(down))
            except Exception:
                pass
        except Exception:
            log.exception("watchdog restart failed")
