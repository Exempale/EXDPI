"""Диагностика DPI-обхода: проверяем, можем ли мы установить TLS-handshake
с заданным SNI на 443/tcp.

Идея простая: TLS-handshake к youtube.com/discord.com/grok.com и т.п.
- если он быстрый и успешный — DPI пропускает; если зависает или падает
с RST/закрытием — DPI режет и без обхода ничего не выйдет.

Ничего не пишет в сеть кроме самих handshake'ов.
"""
from __future__ import annotations

import logging
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

log = logging.getLogger("dpibypass.dpitest")


@dataclass
class TestResult:
    host: str
    ok: bool
    elapsed_ms: int
    error: str = ""


# Набор популярных доменов для проверки. Подобраны так, чтобы покрывать
# разные категории (видео, чат, ИИ, российский DPI любит резать всё это).
DEFAULT_TARGETS: List[str] = [
    "youtube.com",
    "discord.com",
    "chatgpt.com",
    "claude.ai",
    "grok.com",
    "app.devin.ai",
]


def _tls_handshake(host: str, port: int = 443, timeout: float = 5.0) -> TestResult:
    """Пытаемся открыть TCP+TLS до host:port с правильным SNI.

    Возвращает TestResult: ok=True если рукопожатие прошло, иначе ok=False
    с пояснением в .error.
    """
    t0 = time.monotonic()
    sock: Optional[socket.socket] = None
    ssock: Optional[ssl.SSLSocket] = None
    try:
        ctx = ssl.create_default_context()
        # нам не нужна проверка цепочки — нас интересует прошёл ли handshake
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        sock = socket.create_connection((host, port), timeout=timeout)
        ssock = ctx.wrap_socket(sock, server_hostname=host)
        # на этом этапе TLS handshake уже завершён (wrap_socket блокирует)
        elapsed = int((time.monotonic() - t0) * 1000)
        return TestResult(host=host, ok=True, elapsed_ms=elapsed)
    except socket.timeout:
        elapsed = int((time.monotonic() - t0) * 1000)
        return TestResult(host=host, ok=False, elapsed_ms=elapsed, error="timeout")
    except socket.gaierror as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        return TestResult(host=host, ok=False, elapsed_ms=elapsed, error=f"dns: {exc.strerror or exc}")
    except ssl.SSLError as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        return TestResult(host=host, ok=False, elapsed_ms=elapsed, error=f"tls: {exc.reason or exc}")
    except OSError as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        # 10054 (Connection reset) — типичный признак активной DPI-блокировки
        msg = str(exc.strerror or exc)
        if "10054" in msg or "reset" in msg.lower():
            msg = "сброс соединения (DPI режет)"
        return TestResult(host=host, ok=False, elapsed_ms=elapsed, error=msg)
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        return TestResult(host=host, ok=False, elapsed_ms=elapsed, error=str(exc))
    finally:
        for s in (ssock, sock):
            if s is None:
                continue
            try:
                s.close()
            except Exception:
                pass


def run_tests(
    targets: Optional[List[str]] = None,
    timeout: float = 5.0,
    on_progress: Optional[Callable[[TestResult], None]] = None,
) -> List[TestResult]:
    """Прогоняет TLS-handshake по списку хостов последовательно.

    Если передан on_progress — он вызывается после каждого хоста.
    Возвращает полный список результатов.
    """
    targets = targets or DEFAULT_TARGETS
    out: List[TestResult] = []
    for host in targets:
        res = _tls_handshake(host, timeout=timeout)
        out.append(res)
        if on_progress:
            try:
                on_progress(res)
            except Exception:
                log.exception("on_progress callback failed")
    return out


def run_async(
    targets: Optional[List[str]] = None,
    timeout: float = 5.0,
    on_progress: Optional[Callable[[TestResult], None]] = None,
    on_done: Optional[Callable[[List[TestResult]], None]] = None,
) -> threading.Thread:
    """То же что run_tests, но в фоновом потоке. Колбэки вызываются
    из этого потока — UI должен сам бунсить через self.after(0, ...)."""

    def _work():
        results = run_tests(targets=targets, timeout=timeout, on_progress=on_progress)
        if on_done:
            try:
                on_done(results)
            except Exception:
                log.exception("on_done callback failed")

    th = threading.Thread(target=_work, daemon=True, name="dpi-test")
    th.start()
    return th
