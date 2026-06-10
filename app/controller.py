"""Контроллер: одна точка управления состоянием (zapret + proxy)."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Optional

from . import config as appconfig
from .proxy_runner import ProxyRunner
from .securedns import SecureDNSRunner
from .strategy_auto import is_auto, resolve_strategy
from .zapret_runner import ZapretRunner

log = logging.getLogger("dpibypass.ctl")


class Controller:
    def __init__(self) -> None:
        self.cfg: Dict = appconfig.load()
        self.zapret = ZapretRunner()
        self.proxy = ProxyRunner()
        self.securedns = SecureDNSRunner()
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
                and (not self.cfg.get("securedns_enabled", False) or self.securedns.is_running)
            )

    def active_strategy(self) -> str:
        """Реальное имя .bat с учётом режима «Авто» (для запуска и статуса)."""
        return resolve_strategy(self.cfg)

    def is_auto_strategy(self) -> bool:
        return is_auto(str(self.cfg.get("zapret_strategy", "")))

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
                    self.active_strategy(),
                    on_exit=self._zapret_exit,
                    custom_domains=list(self.cfg.get("custom_domains") or []),
                    game_mode=str(self.cfg.get("game_mode", "normal")),
                )
            if self.cfg.get("securedns_enabled", False):
                self.securedns.start(self.cfg, on_error=self._securedns_error)
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
        try:
            self.securedns.stop()
        except Exception:
            log.exception("securedns stop")
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

    def _securedns_error(self, msg: str) -> None:
        if self._on_error:
            self._on_error(msg)
        if self._on_state:
            self._on_state(self.is_on())

    def _proxy_error(self, msg: str) -> None:
        if self._on_error:
            self._on_error(msg)
        if self._on_state:
            self._on_state(self.is_on())
