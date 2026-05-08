"""Контроллер: одна точка управления состоянием (zapret + proxy)."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Optional

from . import config as appconfig
from .proxy_runner import ProxyRunner
from .zapret_runner import ZapretRunner

log = logging.getLogger("dpibypass.ctl")


class Controller:
    def __init__(self) -> None:
        self.cfg: Dict = appconfig.load()
        self.zapret = ZapretRunner()
        self.proxy = ProxyRunner()
        self._lock = threading.Lock()
        self._on_state: Optional[Callable[[bool], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._target_on = False

    # ── observability ────────────────────────────────────────────────
    def bind(
        self,
        on_state: Optional[Callable[[bool], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_state = on_state
        self._on_error = on_error

    def is_on(self) -> bool:
        with self._lock:
            return self._target_on and (
                (not self.cfg.get("zapret_enabled", True) or self.zapret.is_running)
                and (not self.cfg.get("proxy_enabled", True) or self.proxy.is_running)
            )

    # ── config ────────────────────────────────────────────────────────
    def update_cfg(self, **changes) -> None:
        self.cfg.update(changes)
        appconfig.save(self.cfg)

    def save(self) -> None:
        appconfig.save(self.cfg)

    # ── lifecycle ─────────────────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            self._target_on = True
        self.proxy.reset_stats()

        try:
            if self.cfg.get("proxy_enabled", True):
                self.proxy.start(self.cfg, on_error=self._proxy_error)
            if self.cfg.get("zapret_enabled", True):
                self.zapret.start(
                    self.cfg.get("zapret_strategy", "general.bat"),
                    on_exit=self._zapret_exit,
                )
        except Exception as exc:
            log.exception("start failed")
            if self._on_error:
                self._on_error(str(exc))
            self.stop()
            return

        if self._on_state:
            self._on_state(True)

    def stop(self) -> None:
        with self._lock:
            self._target_on = False
        try:
            self.zapret.stop()
        except Exception:
            log.exception("zapret stop")
        try:
            self.proxy.stop()
        except Exception:
            log.exception("proxy stop")
        if self._on_state:
            self._on_state(False)

    def restart_with_new_config(self) -> None:
        was_on = self.is_on() or self._target_on
        if was_on:
            self.stop()
        self.save()
        if was_on:
            self.start()

    # ── callbacks from runners ────────────────────────────────────────
    def _zapret_exit(self, rc: int) -> None:
        log.info("zapret exited rc=%d", rc)
        if rc != 0 and self._target_on and self._on_error:
            self._on_error(f"zapret завершился с кодом {rc}")
        if self._target_on and self._on_state:
            self._on_state(self.is_on())

    def _proxy_error(self, msg: str) -> None:
        if self._on_error:
            self._on_error(msg)
        if self._on_state:
            self._on_state(self.is_on())
