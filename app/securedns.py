"""Защищённый DNS (DoH / DoT) — локальный резолвер.

Поднимает локальный DNS-сервер на 127.0.0.1 (UDP + TCP, порт 53) и пересылает
все запросы к выбранному провайдеру по шифрованному каналу:

* **DoH** — DNS-over-HTTPS (RFC 8484, POST application/dns-message, порт 443);
* **DoT** — DNS-over-TLS  (RFC 7858, TLS-сокет с 2-байтовым префиксом, порт 853).

Зачем: провайдерский DPI часто перехватывает/подменяет обычный DNS (порт 53),
из-за чего обход не работает даже с zapret. Шифрованный DNS закрывает эту дыру.

К провайдерам ходим напрямую по их известным IP (bootstrap) — рекурсивного
резолва имени провайдера не требуется, «курицы и яйца» нет. Сертификат
проверяется штатно (SNI = hostname провайдера).

Опция «назначить системным DNS»: через PowerShell прописывает 127.0.0.1 на
все активные адаптеры, предыдущие значения сохраняет в dns-backup.json и
восстанавливает при выключении.
"""
from __future__ import annotations

import json
import logging
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .config import app_dir

log = logging.getLogger("dpibypass.securedns")


# ── провайдеры ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    hostname: str          # SNI / Host для DoH и DoT
    ips: Tuple[str, ...]   # bootstrap-IP (обходимся без резолва hostname)
    doh_path: str = "/dns-query"


PROVIDERS: List[Provider] = [
    Provider("cloudflare", "Cloudflare (1.1.1.1)", "cloudflare-dns.com", ("1.1.1.1", "1.0.0.1")),
    Provider("google", "Google (8.8.8.8)", "dns.google", ("8.8.8.8", "8.8.4.4")),
    Provider("quad9", "Quad9 (9.9.9.9)", "dns.quad9.net", ("9.9.9.9", "149.112.112.112")),
    Provider("adguard", "AdGuard DNS", "dns.adguard-dns.com", ("94.140.14.14", "94.140.15.15")),
]

DEFAULT_PROVIDER = "cloudflare"
PROTOCOLS = ("doh", "dot")

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 53

_QUERY_TIMEOUT = 5.0
_CACHE_TTL = 60.0
_CACHE_MAX = 4096


def provider_by_id(provider_id: str) -> Provider:
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    return PROVIDERS[0]


def provider_labels() -> Dict[str, str]:
    return {p.id: p.label for p in PROVIDERS}


# ── транспорты (DoH / DoT) ───────────────────────────────────────────


class _BaseTransport:
    """Общее: персистентное TLS-соединение с lock'ом и одним ретраем."""

    def __init__(self, provider: Provider, timeout: float = _QUERY_TIMEOUT) -> None:
        self._provider = provider
        self._timeout = timeout
        self._lock = threading.Lock()
        self._sock: Optional[ssl.SSLSocket] = None
        self._ip_idx = 0

    @property
    def port(self) -> int:  # переопределяется
        raise NotImplementedError

    def _connect(self) -> ssl.SSLSocket:
        last_exc: Optional[Exception] = None
        ips = self._provider.ips
        for attempt in range(len(ips)):
            ip = ips[(self._ip_idx + attempt) % len(ips)]
            try:
                ctx = ssl.create_default_context()
                raw = socket.create_connection((ip, self.port), timeout=self._timeout)
                ssock = ctx.wrap_socket(raw, server_hostname=self._provider.hostname)
                ssock.settimeout(self._timeout)
                self._ip_idx = (self._ip_idx + attempt) % len(ips)
                log.debug("%s connected to %s:%d", type(self).__name__, ip, self.port)
                return ssock
            except Exception as exc:
                last_exc = exc
                continue
        raise ConnectionError(f"не удалось подключиться к {self._provider.hostname}: {last_exc}")

    def _close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def close(self) -> None:
        with self._lock:
            self._close()

    def query(self, payload: bytes) -> bytes:
        """Отправить сырое DNS-сообщение, вернуть сырое DNS-сообщение ответа."""
        with self._lock:
            for attempt in (1, 2):  # один ретрай с переподключением
                try:
                    if self._sock is None:
                        self._sock = self._connect()
                    return self._exchange(self._sock, payload)
                except Exception:
                    self._close()
                    if attempt == 2:
                        raise
        raise ConnectionError("unreachable")

    def _exchange(self, sock: ssl.SSLSocket, payload: bytes) -> bytes:
        raise NotImplementedError


class DoHTransport(_BaseTransport):
    """DNS-over-HTTPS: POST application/dns-message (RFC 8484), HTTP/1.1 keep-alive."""

    port = 443

    def _exchange(self, sock: ssl.SSLSocket, payload: bytes) -> bytes:
        req = (
            f"POST {self._provider.doh_path} HTTP/1.1\r\n"
            f"Host: {self._provider.hostname}\r\n"
            "Accept: application/dns-message\r\n"
            "Content-Type: application/dns-message\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        ).encode("ascii") + payload
        sock.sendall(req)

        # ── читаем заголовки ─────────────────────────────────────────
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("соединение закрыто во время ответа")
            buf += chunk
            if len(buf) > 64 * 1024:
                raise ValueError("слишком длинные HTTP-заголовки")
        head, body = buf.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        status_parts = lines[0].split(" ", 2)
        status = int(status_parts[1]) if len(status_parts) >= 2 else 0
        if status != 200:
            raise ValueError(f"DoH HTTP {status}")
        headers = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        # ── тело: content-length или chunked ───────────────────────
        if headers.get("transfer-encoding", "").lower() == "chunked":
            return self._read_chunked(sock, body)
        length = int(headers.get("content-length", "0"))
        if length <= 0 or length > 65535:
            raise ValueError(f"подозрительный content-length: {length}")
        while len(body) < length:
            chunk = sock.recv(length - len(body))
            if not chunk:
                raise ConnectionError("обрыв тела ответа")
            body += chunk
        return body[:length]

    @staticmethod
    def _read_chunked(sock: ssl.SSLSocket, buf: bytes) -> bytes:
        out = b""
        while True:
            while b"\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("обрыв chunked-ответа")
                buf += chunk
            size_line, buf = buf.split(b"\r\n", 1)
            size = int(size_line.split(b";")[0].strip() or b"0", 16)
            if size == 0:
                return out
            while len(buf) < size + 2:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("обрыв chunked-ответа")
                buf += chunk
            out += buf[:size]
            buf = buf[size + 2:]  # съесть CRLF после чанка
            if len(out) > 65535:
                raise ValueError("слишком длинный DNS-ответ")


class DoTTransport(_BaseTransport):
    """DNS-over-TLS: 2-байтовый length-prefix поверх TLS:853 (RFC 7858)."""

    port = 853

    def _exchange(self, sock: ssl.SSLSocket, payload: bytes) -> bytes:
        sock.sendall(struct.pack("!H", len(payload)) + payload)
        hdr = self._recv_exact(sock, 2)
        (length,) = struct.unpack("!H", hdr)
        if length == 0 or length > 65535:
            raise ValueError(f"битый length-prefix: {length}")
        return self._recv_exact(sock, length)

    @staticmethod
    def _recv_exact(sock: ssl.SSLSocket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("соединение закрыто")
            buf += chunk
        return buf


def make_transport(protocol: str, provider: Provider) -> _BaseTransport:
    if protocol == "dot":
        return DoTTransport(provider)
    return DoHTransport(provider)


# ── локальный DNS-сервер ─────────────────────────────────────────────


class SecureDNSServer:
    """UDP+TCP сервер на 127.0.0.1:53, форвардит запросы через DoH/DoT.

    Сырые DNS-сообщения пересылаются как есть — парсинга пакетов не требуется
    (только подмена ID при ответе из кэша).
    """

    def __init__(self) -> None:
        self._udp: Optional[socket.socket] = None
        self._tcp: Optional[socket.socket] = None
        self._pool: Optional[ThreadPoolExecutor] = None
        self._transport: Optional[_BaseTransport] = None
        self._stop_ev = threading.Event()
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()
        # кэш: key=тело запроса без ID → (expires_at, response)
        self._cache: Dict[bytes, Tuple[float, bytes]] = {}
        self._cache_lock = threading.Lock()
        self.queries = 0
        self.errors = 0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._threads) and any(t.is_alive() for t in self._threads)

    def start(self, protocol: str, provider_id: str,
              host: str = LISTEN_HOST, port: int = LISTEN_PORT) -> None:
        with self._lock:
            if self._threads and any(t.is_alive() for t in self._threads):
                return
            provider = provider_by_id(provider_id)
            self._transport = make_transport(protocol, provider)
            self._stop_ev.clear()
            self._cache.clear()
            self.queries = 0
            self.errors = 0

            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                udp.bind((host, port))
            except OSError as exc:
                udp.close()
                raise RuntimeError(
                    f"порт {port}/udp занят (другой DNS-сервис?): {exc}"
                ) from exc

            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                tcp.bind((host, port))
                tcp.listen(16)
            except OSError as exc:
                udp.close()
                tcp.close()
                raise RuntimeError(
                    f"порт {port}/tcp занят (другой DNS-сервис?): {exc}"
                ) from exc

            udp.settimeout(0.5)
            tcp.settimeout(0.5)
            self._udp, self._tcp = udp, tcp
            self._pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="securedns")

            self._threads = [
                threading.Thread(target=self._udp_loop, daemon=True, name="securedns-udp"),
                threading.Thread(target=self._tcp_loop, daemon=True, name="securedns-tcp"),
            ]
            for t in self._threads:
                t.start()
            log.info(
                "SecureDNS started on %s:%d via %s/%s",
                host, port, protocol, provider.hostname,
            )

    def stop(self) -> None:
        with self._lock:
            self._stop_ev.set()
            threads = list(self._threads)
            self._threads = []
        for t in threads:
            try:
                t.join(timeout=2.0)
            except Exception:
                pass
        for s in (self._udp, self._tcp):
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
        self._udp = self._tcp = None
        if self._pool is not None:
            try:
                self._pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self._pool.shutdown(wait=False)
            self._pool = None
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        log.info("SecureDNS stopped")

    # ── приём запросов ───────────────────────────────────────────────

    def _udp_loop(self) -> None:
        sock = self._udp
        pool = self._pool
        if sock is None or pool is None:
            return
        while not self._stop_ev.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) < 12:
                continue
            try:
                pool.submit(self._handle_udp, data, addr)
            except RuntimeError:
                break

    def _tcp_loop(self) -> None:
        sock = self._tcp
        pool = self._pool
        if sock is None or pool is None:
            return
        while not self._stop_ev.is_set():
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                pool.submit(self._handle_tcp, conn)
            except RuntimeError:
                try:
                    conn.close()
                except Exception:
                    pass
                break

    # ── обработка ────────────────────────────────────────────────────

    def _resolve(self, query: bytes) -> Optional[bytes]:
        """Резолв через кэш или транспорт. Ответ уже с ID запроса."""
        qid = query[:2]
        key = bytes(query[2:])
        now = time.monotonic()
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                return qid + hit[1][2:]

        transport = self._transport
        if transport is None:
            return None
        self.queries += 1
        try:
            resp = transport.query(query)
        except Exception as exc:
            self.errors += 1
            log.warning("resolve failed: %s", exc)
            return None
        if len(resp) < 12:
            return None
        with self._cache_lock:
            if len(self._cache) >= _CACHE_MAX:
                self._cache.clear()
            self._cache[key] = (now + _CACHE_TTL, resp)
        return qid + resp[2:]

    def _handle_udp(self, query: bytes, addr: Tuple[str, int]) -> None:
        resp = self._resolve(query)
        if resp is None or self._udp is None:
            return
        try:
            self._udp.sendto(resp, addr)
        except OSError:
            pass

    def _handle_tcp(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(_QUERY_TIMEOUT)
            hdr = self._recv_exact(conn, 2)
            if hdr is None:
                return
            (length,) = struct.unpack("!H", hdr)
            if length == 0 or length > 65535:
                return
            query = self._recv_exact(conn, length)
            if query is None or len(query) < 12:
                return
            resp = self._resolve(query)
            if resp is None:
                return
            conn.sendall(struct.pack("!H", len(resp)) + resp)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> Optional[bytes]:
        buf = b""
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
            except Exception:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf


# ── системный DNS (Windows) ──────────────────────────────────────────

_DNS_BACKUP_FILE = "dns-backup.json"


def _run_powershell(command: str, timeout: float = 20.0) -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        CREATE_NO_WINDOW = 0x08000000
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout,
        )
        if result.returncode != 0:
            log.warning("powershell rc=%d: %s", result.returncode,
                        result.stderr.decode("utf-8", errors="replace")[:300])
            return None
        return result.stdout.decode("utf-8", errors="replace")
    except Exception:
        log.exception("powershell failed")
        return None


def _backup_path() -> Path:
    return app_dir() / _DNS_BACKUP_FILE


def set_system_dns(server: str = LISTEN_HOST) -> bool:
    """Прописать ``server`` как DNS на все активные адаптеры.

    Текущие значения сохраняются в dns-backup.json (если бэкапа ещё нет —
    т.е. не перетираем бэкап при повторном включении).
    """
    if sys.platform != "win32":
        return False
    out = _run_powershell(
        "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | ForEach-Object { "
        "[PSCustomObject]@{ Index=$_.InterfaceIndex; Alias=$_.Name; "
        "Servers=@((Get-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex "
        "-AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses) } } "
        "| ConvertTo-Json -Depth 3"
    )
    if not out:
        return False
    try:
        adapters = json.loads(out)
        if isinstance(adapters, dict):
            adapters = [adapters]
    except Exception:
        log.exception("failed to parse adapter list")
        return False

    # не перетираем существующий бэкап «нашими» 127.0.0.1
    try:
        if not _backup_path().exists():
            _backup_path().parent.mkdir(parents=True, exist_ok=True)
            _backup_path().write_text(
                json.dumps(adapters, ensure_ascii=False, indent=2), encoding="utf-8",
            )
    except Exception:
        log.exception("failed to write dns backup")
        return False

    ok_any = False
    for ad in adapters:
        idx = ad.get("Index")
        if idx is None:
            continue
        res = _run_powershell(
            f"Set-DnsClientServerAddress -InterfaceIndex {int(idx)} "
            f"-ServerAddresses '{server}'"
        )
        if res is not None:
            ok_any = True
    if ok_any:
        flush_dns_cache()
        log.info("system DNS set to %s on %d adapter(s)", server, len(adapters))
    return ok_any


def restore_system_dns() -> bool:
    """Вернуть DNS-настройки адаптеров из бэкапа (и удалить бэкап)."""
    if sys.platform != "win32":
        return False
    path = _backup_path()
    if not path.exists():
        return True
    try:
        adapters = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(adapters, dict):
            adapters = [adapters]
    except Exception:
        log.exception("failed to read dns backup")
        return False

    ok = True
    for ad in adapters:
        idx = ad.get("Index")
        if idx is None:
            continue
        servers = [s for s in (ad.get("Servers") or []) if s and s != LISTEN_HOST]
        if servers:
            quoted = ",".join(f"'{s}'" for s in servers)
            cmd = (f"Set-DnsClientServerAddress -InterfaceIndex {int(idx)} "
                   f"-ServerAddresses {quoted}")
        else:
            cmd = (f"Set-DnsClientServerAddress -InterfaceIndex {int(idx)} "
                   f"-ResetServerAddresses")
        if _run_powershell(cmd) is None:
            ok = False
    if ok:
        try:
            path.unlink()
        except Exception:
            pass
        flush_dns_cache()
        log.info("system DNS restored")
    return ok


def flush_dns_cache() -> None:
    if sys.platform != "win32":
        return
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(
            ["ipconfig", "/flushdns"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=10,
        )
    except Exception:
        pass


# ── фасад для контроллера ────────────────────────────────────────────


class SecureDNSRunner:
    """Управляет сервером + системным DNS по конфигу приложения."""

    def __init__(self) -> None:
        self._server = SecureDNSServer()
        self._system_dns_set = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._server.is_running

    def stats(self) -> Dict[str, int]:
        return {"queries": self._server.queries, "errors": self._server.errors}

    def start(self, cfg: Dict, on_error: Optional[Callable[[str], None]] = None) -> None:
        with self._lock:
            if self._server.is_running:
                return
            protocol = str(cfg.get("securedns_protocol", "doh"))
            provider = str(cfg.get("securedns_provider", DEFAULT_PROVIDER))
            try:
                self._server.start(protocol, provider)
            except Exception as exc:
                log.exception("SecureDNS start failed")
                if on_error:
                    on_error(f"DNS: {exc}")
                return
            if bool(cfg.get("securedns_set_system", True)):
                try:
                    self._system_dns_set = set_system_dns()
                except Exception:
                    log.exception("set system dns failed")
                    self._system_dns_set = False

    def stop(self) -> None:
        with self._lock:
            try:
                self._server.stop()
            except Exception:
                log.exception("SecureDNS server stop failed")
            if self._system_dns_set:
                try:
                    restore_system_dns()
                except Exception:
                    log.exception("restore system dns failed")
                self._system_dns_set = False
