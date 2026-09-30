"""Мониторинг сервисов + автопереключение стратегий (появилось в 3.0).

Раз в ``hc_interval_min`` минут проверяет, что сервисы реально ОТКРЫВАЮТСЯ:
DoH-резолв (обход подмены DNS, из-за которой браузер с «безопасным DNS»
работал, а наш щуп падал) → TLS к настоящему IP → HTTP GET и проверка
статуса. В мониторинг берутся только сервисы, которые режутся DPI и
обходятся zapret'ом (YouTube, Discord, Roblox): geo-блоки компаний
(OpenAI, Meta) zapret обойти не может — там щуп всегда был бы красным.

Контрольный хост (google generate_204) отличает «DPI задушил сервис» от
«интернета нет вообще»: если контрольный лежит — ничего не переключаем.

Поведение при падении сервиса:
  * индикаторы в главном окне краснеют (колбэк ``on_status``);
  * если включено ``hc_autoswitch`` и мы в DPI-режиме — перебирает
    остальные стратегии: рестарт zapret → проверка → остаётся на первой
    рабочей. Если zapret вообще не стартует (мгновенный выход, напр.
    вторая копия EXDPI держит WinDivert) — автопереключение аварийно
    останавливается, чтобы не устраивать шторм рестартов.

Поток один, daemon. Все колбэки зовутся из рабочего потока — UI обязан
маршаллить через ``after(0, ...)``. Рестарты сериализуются lifecycle-локом
контроллера; на время переключения watchdog ставится на паузу.
"""
from __future__ import annotations

import json
import logging
import ssl
import socket
import threading
import time
from typing import Callable, Dict, List, Optional, Set, Tuple

from .i18n import t

log = logging.getLogger("dpibypass.healthcheck")

# сервисы для мониторинга: (имя для UI, хост, путь, ожидаемые HTTP-статусы)
# это сервисы, которые блокируются именно DPI и обходятся zapret'ом.
# Roblox заблокирован РКН по SNI и есть в пресете «Игры» (как и Discord);
# Instagram/ChatGPT не подходят — их режут не DPI, а geo-блоки компаний.
SERVICES: List[Tuple[str, str, str, Set[int]]] = [
    ("YouTube", "www.youtube.com", "/generate_204", {204}),
    ("Discord", "discord.com", "/api/v9/gateway", {200}),
    ("Roblox", "www.roblox.com", "/robots.txt", {200}),
]
_CONTROL = ("www.google.com", "/generate_204", {204, 301, 302})
_SETTLE_SECONDS = 4.0          # пауза после рестарта zapret перед пробой
_MAX_DEAD_STARTS = 2           # столько мгновенных смертей winws — и стоп

_DOH_PROVIDERS = (
    "https://1.1.1.1/dns-query?name={host}&type=A",
    "https://dns.google/resolve?name={host}&type=A",
)


def _doh_resolve(host: str) -> Optional[str]:
    """Резолв через DoH (1.1.1.1 → dns.google → системный DNS).

    Системный DNS в РФ подменяет адреса заблокированных доменов — из-за
    этого щуп без DoH показывал «сервис лежит», хотя в браузере (с шифро-
    ванным DNS) всё работало.
    """
    for tpl in _DOH_PROVIDERS:
        data = _fetch_json(tpl.format(host=host))
        if data is None:
            continue
        answers = [a for a in data.get("Answer", []) if a.get("type") == 1]
        if answers:
            return str(answers[0]["data"])
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass
    return None


def _fetch_json(url: str, timeout: float = 4.0):
    try:
        import urllib.request
        req = urllib.request.Request(
            url, headers={"accept": "application/dns-json",
                          "User-Agent": "EXDPI/"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _http_probe(host: str, path: str, ok_statuses: Set[int],
                ip: Optional[str], timeout: float = 5.0) -> bool:
    """TLS к реальному IP (SNI=host) + HTTP GET → статус в ok_statuses?"""
    target = ip or host
    sock: Optional[socket.socket] = None
    ssock: Optional[ssl.SSLSocket] = None
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        sock = socket.create_connection((target, 443), timeout=timeout)
        ssock = ctx.wrap_socket(sock, server_hostname=host)
        ssock.settimeout(timeout)
        req = (f"GET {path} HTTP/1.1\r\n"
               f"Host: {host}\r\n"
               "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) EXDPI/\r\n"
               "Accept: */*\r\n"
               "Connection: close\r\n\r\n")
        ssock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n" not in buf and len(buf) < 8192:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            buf += chunk
        first = buf.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = first.split(" ")
        if len(parts) >= 2 and parts[0].startswith("HTTP/"):
            try:
                return int(parts[1]) in ok_statuses
            except ValueError:
                return False
        return False
    except Exception:
        return False
    finally:
        for s in (ssock, sock):
            if s is None:
                continue
            try:
                s.close()
            except Exception:
                pass


class HealthChecker:
    def __init__(self, ctl, on_status: Callable[[Dict[str, Optional[bool]], bool], None],
                 on_notify: Callable[[str], None], stop_event: Optional[threading.Event] = None) -> None:
        self.ctl = ctl
        self._on_status = on_status
        self._on_notify = on_notify
        self._stop = stop_event or threading.Event()
        self._thread: threading.Thread | None = None
        self._switch_lock = threading.Lock()
        self._force = threading.Event()   # внеочередной тик (после включения)
        self.last_results: Dict[str, Optional[bool]] = {
            name: None for name, _h, _p, _s in SERVICES}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="healthcheck")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def request_tick(self) -> None:
        """Внеочередная проверка (пользователь включил обход — не ждать
        интервала, точки должны обновиться быстро)."""
        self._force.set()

    # ── внутреннее ───────────────────────────────────────────────────
    def _loop(self) -> None:
        # первый тик — через 90 секунд: за это время пользователь успеет
        # включить обход, а ядрам — подняться; раньше точки застывали
        # красными от промера «в момент до включения»
        next_in = 90.0
        while not self._stop.is_set():
            deadline = time.monotonic() + next_in
            while not self._stop.is_set() and not self._force.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if self._stop.wait(min(5.0, remaining)):
                    return
            if self._stop.is_set():
                return
            self._force.clear()
            try:
                cfg = self.ctl.cfg
                if not bool(cfg.get("hc_enabled", True)):
                    next_in = 30.0
                    continue
                try:
                    minutes = int(cfg.get("hc_interval_min", 5))
                except (TypeError, ValueError):
                    minutes = 5
                next_in = max(2, minutes) * 60.0
                self.tick()
            except Exception:
                log.exception("healthcheck tick failed")
                next_in = 60.0

    def tick(self) -> None:
        """Одна проверка: контрольный хост + сервисы, при падении — реконфиг."""
        ctl_h, ctl_path, ctl_ok = _CONTROL
        network_ok = _http_probe(ctl_h, ctl_path, ctl_ok,
                                 _doh_resolve(ctl_h), timeout=4.0)
        results: Dict[str, Optional[bool]] = {}
        ips: Dict[str, Optional[str]] = {}
        for name, host, path, ok in SERVICES:
            ip = ips.get(host) or _doh_resolve(host)
            ips[host] = ip
            results[name] = _http_probe(host, path, ok, ip) if ip else False
        self.last_results = dict(results)
        self._report(results, network_ok)

        broken = [name for name, ok in results.items() if not ok]
        if not broken or not network_ok:
            return
        if not bool(self.ctl.cfg.get("hc_autoswitch", True)):
            return
        if self.ctl.is_vpn:
            return  # в VPN-режиме стратегий нет — только сигнал в UI
        if not self.ctl.is_target_on():
            return
        self._autoswitch(broken)

    def _report(self, results: Dict[str, Optional[bool]], network_ok: bool) -> None:
        try:
            self._on_status(dict(results), network_ok)
        except Exception:
            log.exception("on_status callback failed")

    def _autoswitch(self, broken: List[str]) -> None:
        """Перебрать стратегии, оставить первую, при которой всё открылось."""
        if not self._switch_lock.acquire(blocking=False):
            return  # уже идёт переключение
        try:
            from .strategy_auto import is_auto
            from .zapret_runner import list_strategies

            cfg = self.ctl.cfg
            current = str(cfg.get("zapret_strategy", ""))
            if is_auto(current):
                return  # режим «Авто» сам разбирается
            original = current
            candidates = [s for s in list_strategies() if s != original]
            log.warning("healthcheck: сервисы легли (%s), подбираю стратегию",
                        ", ".join(broken))
            # watchdog отдыхает, пока мы сами перебираем стратегии
            setattr(self.ctl, "suppress_watchdog", True)
            dead_starts = 0

            for cand in candidates:
                cfg["zapret_strategy"] = cand
                self.ctl.restart_with_new_config()
                time.sleep(_SETTLE_SECONDS)
                if hasattr(self.ctl, "zapret") and not self.ctl.zapret.is_running:
                    # winws умер сразу после старта (код 1 и т.п.): стратегия
                    # тут ни при чём — дальше перебирать бессмысленно
                    dead_starts += 1
                    log.warning("healthcheck: %s не стартовал, попытка %d",
                                cand, dead_starts)
                    if dead_starts >= _MAX_DEAD_STARTS:
                        cfg["zapret_strategy"] = original
                        self.ctl.restart_with_new_config()
                        self._notify(t("notify.health_zapret_dead"))
                        return
                    continue
                ok = all(self._probe_service(h, p, s) for _n, h, p, s in SERVICES)
                if ok:
                    self.ctl.save()
                    self._report({n: True for n, _h, _p, _s in SERVICES}, True)
                    log.info("healthcheck: подошла стратегия %s", cand)
                    self._notify(t("notify.health_switched",
                                   old=self._short(original), new=self._short(cand)))
                    return

            cfg["zapret_strategy"] = original
            self.ctl.restart_with_new_config()
            self._notify(t("notify.health_failed", old=self._short(original)))
            log.warning("healthcheck: ни одна стратегия не помогла, откат на %s",
                        original)
        except Exception:
            log.exception("healthcheck autoswitch failed")
        finally:
            setattr(self.ctl, "suppress_watchdog", False)
            self._switch_lock.release()

    @staticmethod
    def _probe_service(host: str, path: str, ok: Set[int]) -> bool:
        return _http_probe(host, path, ok, _doh_resolve(host))

    @staticmethod
    def _short(strategy: str) -> str:
        s = str(strategy)
        return s[:-4] if s.endswith(".bat") else s

    def _notify(self, msg: str) -> None:
        try:
            self._on_notify(msg)
        except Exception:
            log.exception("on_notify callback failed")
