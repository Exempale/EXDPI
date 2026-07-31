"""Запуск tg-ws-proxy в фоновом потоке (внутри процесса GUI)."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from proxy import parse_dc_ip_list, proxy_config
from proxy.stats import stats
from proxy.tg_ws_proxy import _run

log = logging.getLogger("dpibypass.proxy")


class ProxyRunner:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None
        self._lock = threading.Lock()
        self._error: Optional[str] = None
        self._on_error: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> Optional[str]:
        return self._error

    def apply_config(self, cfg: Dict) -> None:
        try:
            dc = parse_dc_ip_list(cfg.get("proxy_dc_ip", ["2:149.154.167.220", "4:149.154.167.220"]))
        except ValueError:
            dc = {2: "149.154.167.220", 4: "149.154.167.220"}
        proxy_config.host = cfg.get("proxy_host", "127.0.0.1")
        proxy_config.port = int(cfg.get("proxy_port", 1443))
        proxy_config.secret = cfg.get("proxy_secret") or "00" * 16
        proxy_config.dc_redirects = dc
        proxy_config.buffer_size = 256 * 1024
        proxy_config.pool_size = 4
        proxy_config.fallback_cfproxy = True
        proxy_config.fallback_cfproxy_priority = True
        proxy_config.cfproxy_user_domain = ""
        proxy_config.fake_tls_domain = ""
        proxy_config.proxy_protocol = False

    def start(self, cfg: Dict, on_error: Optional[Callable[[str], None]] = None) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self.apply_config(cfg)
            self._error = None
            self._on_error = on_error
            self._thread = threading.Thread(
                target=self._run_thread, daemon=True, name="dpibypass-proxy",
            )
            self._thread.start()

    def stop(self, timeout: float = 4.0) -> None:
        with self._lock:
            loop = self._loop
            stop_ev = self._stop
            thread = self._thread

        if loop is None or stop_ev is None:
            return
        try:
            loop.call_soon_threadsafe(stop_ev.set)
        except RuntimeError:
            pass

        if thread:
            thread.join(timeout=timeout)

        with self._lock:
            self._thread = None
            self._loop = None
            self._stop = None

    def _run_thread(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_ev = asyncio.Event()
        with self._lock:
            self._loop = loop
            self._stop = stop_ev
        try:
            loop.run_until_complete(_run(stop_event=stop_ev))
        except Exception as exc:
            msg = repr(exc)
            log.error("proxy crashed: %s", msg)
            self._error = msg
            if self._on_error:
                try:
                    self._on_error(msg)
                except Exception:
                    pass
        finally:
            try:
                loop.close()
            except Exception:
                pass

    # stats helpers
    @staticmethod
    def stats_snapshot() -> Dict[str, int]:
        return {
            "active": stats.connections_active,
            "total": stats.connections_total,
            "ws": stats.connections_ws,
            "errors": stats.ws_errors,
        }

    @staticmethod
    def reset_stats() -> None:
        stats.connections_total = 0
        stats.connections_active = 0
        stats.connections_ws = 0
        stats.connections_tcp_fallback = 0
        stats.connections_cfproxy = 0
        stats.connections_bad = 0
        stats.connections_masked = 0
        stats.ws_errors = 0
        stats.bytes_up = 0
        stats.bytes_down = 0
        stats.pool_hits = 0
        stats.pool_misses = 0
