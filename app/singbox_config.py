"""Парсер VLESS / Shadowsocks и генератор конфига Sing-box (режим TUN).

Превращает ссылку-подключения (``vless://...`` / ``ss://...``) в валидный
dict-конфиг для ядра Sing-box, заточенный под глобальный VPN на Windows:

* ``inbounds``  — единственный TUN-интерфейс (перехватывает весь трафик ОС);
* ``dns``       — двухступенчатая схема: DOH/DOT upstream + детект ru/en,
                  чтобы резолвить российские домены напрямую (иначе до них
                  долго идти через прокси), а остальные — через туннель;
* ``route``     — приватные адреса и DNS-серверы локально, всё остальное — в
                  TUN. ``auto_detect_interface`` сам подставит физический NIC.

Из ``vless://`` поддерживаются Reality, XTLS-Vision/Flow, WS/gRPC/tcp/QUIC,
из ``ss://`` — любой метод, который понимает sing-box (включая chacha20,
aes-256-gcm и 2022-бланки).

Дополнительно поддерживаются ссылки-подписки (``http://`` / ``https://``) —
стандартный механизм V2Ray/sing-box: по URL лежит base64 от списка ссылок
``vless://``/``ss://``, разделённых переводом строки. ``list_servers()``
скачивает и разбирает такую подписку в список серверов для UI (выбор
локации), сам VPN всегда стартует по конкретной ``vless://``/``ss://``
ссылке — выбор одного сервера из подписки происходит на уровне UI.

API:
    parse_uri(uri)                 -> dict   (распарсенные поля)
    is_subscription_url(s)         -> bool   (http:// / https://)
    fetch_subscription(url)        -> list[str]  (ссылки из подписки)
    list_servers(uri_or_sub)       -> list[dict]  ([{"tag","uri"}, ...])
    build_config(uri)              -> dict   (готовый singbox config)
    save_config(uri, path=None)    -> Path   (записать singbox_config.json)
    ParseError                              (невалидная ссылка / формат)
"""
from __future__ import annotations

import base64
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import countries, hwid, paths

log = logging.getLogger("dpibypass.singbox.cfg")


class ParseError(ValueError):
    """Невалидная или неподдерживаемая ссылка."""


# ─────────────────────────────────────────────────────────────────────────────
#  Базовые хелперы
# ─────────────────────────────────────────────────────────────────────────────
def _b64decode_loose(data: str) -> bytes:
    """Base64-декодинг, устойчивый к отсутствующим padding/whitespace.

    Shadowsocks-ссылки исторически гуляют без ``==`` и с ``+`` / ``/`` либо
    base64url-символами. Приводим к canonical base64, добиваем padding.
    """
    s = data.strip().replace("\n", "").replace("\r", "")
    # base64url → base64
    s = s.replace("-", "+").replace("_", "/")
    pad = (-len(s)) % 4
    s += "=" * pad
    return base64.b64decode(s, validate=False)


def _split_host_port(netloc: str) -> Tuple[str, Optional[int]]:
    """Разобрать ``host:port`` с учётом IPv6 в квадратных скобках."""
    host: str
    port: Optional[int]
    if netloc.startswith("["):
        # [ipv6]:port
        end = netloc.find("]")
        if end == -1:
            raise ParseError(f"незакрытая IPv6-скобка: {netloc!r}")
        host = netloc[1:end]
        rest = netloc[end + 1:]
        port = int(rest[1:]) if rest.startswith(":") else None
    else:
        if ":" in netloc:
            h, _, p = netloc.rpartition(":")
            host = h
            try:
                port = int(p)
            except ValueError as exc:
                raise ParseError(f"невалидный порт: {p!r}") from exc
        else:
            host = netloc
            port = None
    return host, port


# ─────────────────────────────────────────────────────────────────────────────
#  Парсеры схем
# ─────────────────────────────────────────────────────────────────────────────
def _parse_vless(uri: str) -> Dict[str, Any]:
    """``vless://uuid@host:port?params#tag`` → словарь полей."""
    if not uri.lower().startswith("vless://"):
        raise ParseError("ожидается vless:// ссылка")
    parsed = urllib.parse.urlsplit(uri)
    if not parsed.hostname or not parsed.port or not parsed.username:
        raise ParseError("vless: не хватает uuid/host/port")

    q = urllib.parse.parse_qs(parsed.query)
    # parse_qs даёт списки — разворачиваем одиночные значения
    params = {k: (v[0] if v else "") for k, v in q.items()}

    tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "vless-out"

    # ``type=`` в query — это V2Ray-транспорт (tcp/ws/grpc/http/...), а не
    # sing-box outbound.network (который значит "tcp"/"udp"-only и почти
    # всегда должен быть не задан). Держим отдельно как transport_type,
    # чтобы не перепутать при сборке outbound-а.
    transport_type = params.get("type", "tcp").lower()

    out: Dict[str, Any] = {
        "type": "vless",
        "tag": tag,
        "uuid": parsed.username,
        "server": parsed.hostname,
        "server_port": int(parsed.port),
        "flow": params.get("flow", ""),
        "sni": params.get("sni", ""),
        "alpn": params.get("alpn", ""),
        "fingerprint": params.get("fp", ""),
        "encryption": params.get("encryption", "none"),
    }

    # Reality / TLS
    security = params.get("security", "").lower()
    if security == "reality":
        out["tls"] = {
            "enabled": True,
            "server_name": params.get("sni", params.get("peer", "")),
            "insecure": params.get("allowInsecure", "0") in ("1", "true"),
            "utls": {
                "enabled": True,
                "fingerprint": params.get("fp", "chrome") or "chrome",
            },
            "reality": {
                "enabled": True,
                "public_key": params.get("pbk", ""),
                "short_id": params.get("sid", ""),
            },
        }
    elif security == "tls":
        out["tls"] = {
            "enabled": True,
            "server_name": params.get("sni", params.get("peer", "")),
            "insecure": params.get("allowInsecure", "0") in ("1", "true"),
            "alpn": params.get("alpn", "").split(",") if params.get("alpn") else [],
            "utls": {
                "enabled": bool(params.get("fp")),
                "fingerprint": params.get("fp", "chrome") or "chrome",
            } if params.get("fp") else None,
        }
        # убираем None-поля
        out["tls"] = {k: v for k, v in out["tls"].items() if v not in (None, [], "")}
    elif security:
        log.warning("vless: security=%s не поддерживается, игнорируем", security)

    # Транспорт (V2Ray transport, НЕ outbound.network)
    if transport_type == "ws":
        out["transport"] = {
            "type": "ws",
            "path": params.get("path", "/") or "/",
            "headers": {"Host": params.get("host", params.get("sni", ""))} if
                       (params.get("host") or params.get("sni")) else {},
        }
    elif transport_type == "grpc":
        out["transport"] = {
            "type": "grpc",
            "service_name": params.get("serviceName", ""),
        }
    elif transport_type in ("http", "h2", "httpupgrade"):
        out["transport"] = {
            "type": "http",
            "host": [params.get("host", "")] if params.get("host") else [],
            "path": params.get("path", "/") or "/",
        }
    elif transport_type in ("xhttp", "splithttp"):
        # Новый транспорт 1.10+ — пока отдаём как есть, sing-box поймёт
        out["transport"] = {
            "type": "http",
            "host": [params.get("host", "")] if params.get("host") else [],
            "path": params.get("path", "/") or "/",
        }
    # tcp/quic — transport не нужен

    return out


def _parse_ss(uri: str) -> Dict[str, Any]:
    """``ss://...`` → словарь полей. Поддерживает оба формата:

    1. ``ss://base64(method:password)@host:port#tag``  (SIP002)
    2. ``ss://base64(method:password@host:port)#tag``  (legacy)
    """
    if not uri.lower().startswith("ss://"):
        raise ParseError("ожидается ss:// ссылка")

    rest = uri[len("ss://"):]
    tag = ""
    if "#" in rest:
        rest, tag = rest.split("#", 1)
        tag = urllib.parse.unquote(tag)
    # отрезаем query (для ss почти не используется, но SIP002 допускает)
    rest = rest.split("?", 1)[0]

    method = password = ""
    host: Optional[str] = None
    port: Optional[int] = None

    if "@" in rest:
        # SIP002: userinfo@host:port, userinfo может быть base64 или plain
        userinfo, _, hostport = rest.rpartition("@")
        if not userinfo or not hostport:
            raise ParseError("ss: битая структура userinfo@host:port")
        # base64-encoded userinfo? (SIP002 рекомендует)
        try:
            decoded = _b64decode_loose(userinfo).decode("utf-8", errors="strict")
        except Exception:
            decoded = userinfo  # plaintext method:password
        if ":" not in decoded:
            raise ParseError("ss: нет ':' в method:password")
        method, password = decoded.split(":", 1)
        host, port = _split_host_port(hostport)
    else:
        # legacy: весь остаток — base64(method:password@host:port)
        try:
            decoded = _b64decode_loose(rest).decode("utf-8", errors="strict")
        except Exception as exc:
            raise ParseError("ss: не удалось декодировать base64") from exc
        if "@" not in decoded:
            raise ParseError("ss: нет '@' в декодированной ссылке")
        userinfo, _, hostport = decoded.rpartition("@")
        method, password = userinfo.split(":", 1)
        host, port = _split_host_port(hostport)

    if not host or not port:
        raise ParseError("ss: не разобрать host/port")
    if not method or password == "":
        raise ParseError("ss: не разобрать method/password")

    return {
        "type": "shadowsocks",
        "tag": tag or "ss-out",
        "method": method,
        "password": password,
        "server": host,
        "server_port": port,
    }


def _parse_vmess(uri: str) -> Dict[str, Any]:
    """``vmess://base64(json)`` — формат v2rayN/v2rayNG (самый частый в подписках).

    JSON внутри обычно содержит поля ``v``/``ps``/``add``/``port``/``id``/
    ``aid``/``net``/``type``/``host``/``path``/``tls``/``sni``. Не все
    генераторы подписок кладут одинаковый набор — берём по максимуму,
    недостающее подставляем дефолтами.
    """
    if not uri.lower().startswith("vmess://"):
        raise ParseError("ожидается vmess:// ссылка")
    payload = uri[len("vmess://"):].split("#", 1)[0]
    try:
        raw = _b64decode_loose(payload).decode("utf-8", errors="strict")
        data = json.loads(raw)
    except Exception as exc:
        raise ParseError(f"vmess: не удалось разобрать base64/json: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("vmess: json не является объектом")

    host = str(data.get("add") or "")
    try:
        port = int(data.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    uuid = str(data.get("id") or "")
    if not host or not port or not uuid:
        raise ParseError("vmess: не хватает add/port/id")

    net = str(data.get("net") or "tcp").lower()
    tag = str(data.get("ps") or "vmess-out")

    out: Dict[str, Any] = {
        "type": "vmess",
        "tag": tag,
        "server": host,
        "server_port": port,
        "uuid": uuid,
        "security": str(data.get("scy") or "auto"),
        "alter_id": int(data.get("aid") or 0),
    }

    tls = str(data.get("tls") or "").lower()
    if tls in ("tls", "reality"):
        out["tls"] = {
            "enabled": True,
            "server_name": str(data.get("sni") or data.get("host") or ""),
            "insecure": bool(data.get("allowInsecure")),
        }
        fp = str(data.get("fp") or "")
        if fp:
            out["tls"]["utls"] = {"enabled": True, "fingerprint": fp}
        out["tls"] = {k: v for k, v in out["tls"].items() if v not in (None, [], "")}

    net_type = str(data.get("type") or "")
    if net == "ws":
        out["transport"] = {
            "type": "ws",
            "path": str(data.get("path") or "/") or "/",
            "headers": {"Host": str(data.get("host"))} if data.get("host") else {},
        }
    elif net == "grpc":
        out["transport"] = {
            "type": "grpc",
            "service_name": str(data.get("path") or ""),
        }
    elif net in ("h2", "http"):
        out["transport"] = {
            "type": "http",
            "host": [str(data.get("host"))] if data.get("host") else [],
            "path": str(data.get("path") or "/") or "/",
        }
    elif net == "tcp" and net_type == "http":
        out["transport"] = {
            "type": "http",
            "host": [str(data.get("host"))] if data.get("host") else [],
            "path": str(data.get("path") or "/") or "/",
        }

    return out


def _parse_trojan(uri: str) -> Dict[str, Any]:
    """``trojan://password@host:port?params#tag``."""
    if not uri.lower().startswith("trojan://"):
        raise ParseError("ожидается trojan:// ссылка")
    parsed = urllib.parse.urlsplit(uri)
    if not parsed.hostname or not parsed.port or not parsed.username:
        raise ParseError("trojan: не хватает password/host/port")

    q = urllib.parse.parse_qs(parsed.query)
    params = {k: (v[0] if v else "") for k, v in q.items()}
    tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "trojan-out"
    transport_type = params.get("type", "tcp").lower()

    out: Dict[str, Any] = {
        "type": "trojan",
        "tag": tag,
        "server": parsed.hostname,
        "server_port": int(parsed.port),
        "password": urllib.parse.unquote(parsed.username),
    }

    security = params.get("security", "tls").lower()
    if security != "none":
        out["tls"] = {
            "enabled": True,
            "server_name": params.get("sni", params.get("peer", "")),
            "insecure": params.get("allowInsecure", "0") in ("1", "true"),
        }
        fp = params.get("fp", "")
        if fp:
            out["tls"]["utls"] = {"enabled": True, "fingerprint": fp}
        out["tls"] = {k: v for k, v in out["tls"].items() if v not in (None, [], "")}

    if transport_type == "ws":
        out["transport"] = {
            "type": "ws",
            "path": params.get("path", "/") or "/",
            "headers": {"Host": params.get("host", params.get("sni", ""))} if
                       (params.get("host") or params.get("sni")) else {},
        }
    elif transport_type == "grpc":
        out["transport"] = {
            "type": "grpc",
            "service_name": params.get("serviceName", ""),
        }

    return out


def _parse_hysteria2(uri: str) -> Dict[str, Any]:
    """``hysteria2://password@host:port?params#tag`` (алиас ``hy2://``)."""
    low = uri.lower()
    if not (low.startswith("hysteria2://") or low.startswith("hy2://")):
        raise ParseError("ожидается hysteria2:// ссылка")
    parsed = urllib.parse.urlsplit(uri)
    if not parsed.hostname or not parsed.port:
        raise ParseError("hysteria2: не хватает host/port")

    q = urllib.parse.parse_qs(parsed.query)
    params = {k: (v[0] if v else "") for k, v in q.items()}
    tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "hysteria2-out"
    password = urllib.parse.unquote(parsed.username or "") or params.get("password", "")

    out: Dict[str, Any] = {
        "type": "hysteria2",
        "tag": tag,
        "server": parsed.hostname,
        "server_port": int(parsed.port),
        "password": password,
    }
    obfs = params.get("obfs", "")
    if obfs and obfs.lower() != "none":
        out["obfs"] = {"type": obfs, "password": params.get("obfs-password", "")}
    out["tls"] = {
        "enabled": True,
        "server_name": params.get("sni", params.get("peer", "")),
        "insecure": params.get("insecure", "0") in ("1", "true"),
    }
    out["tls"] = {k: v for k, v in out["tls"].items() if v not in (None, [], "")}
    return out


def _parse_tuic(uri: str) -> Dict[str, Any]:
    """``tuic://uuid:password@host:port?params#tag``."""
    if not uri.lower().startswith("tuic://"):
        raise ParseError("ожидается tuic:// ссылка")
    parsed = urllib.parse.urlsplit(uri)
    if not parsed.hostname or not parsed.port or not parsed.username:
        raise ParseError("tuic: не хватает uuid/host/port")

    q = urllib.parse.parse_qs(parsed.query)
    params = {k: (v[0] if v else "") for k, v in q.items()}
    tag = urllib.parse.unquote(parsed.fragment) if parsed.fragment else "tuic-out"

    out: Dict[str, Any] = {
        "type": "tuic",
        "tag": tag,
        "server": parsed.hostname,
        "server_port": int(parsed.port),
        "uuid": urllib.parse.unquote(parsed.username),
        "password": urllib.parse.unquote(parsed.password or ""),
        "congestion_control": params.get("congestion_control", "bbr"),
        "tls": {
            "enabled": True,
            "server_name": params.get("sni", ""),
            "insecure": params.get("allow_insecure", "0") in ("1", "true"),
            "alpn": params.get("alpn", "").split(",") if params.get("alpn") else ["h3"],
        },
    }
    out["tls"] = {k: v for k, v in out["tls"].items() if v not in (None, [], "")}
    return out


_SCHEME_PARSERS = {
    "vless": _parse_vless,
    "ss": _parse_ss,
    "vmess": _parse_vmess,
    "trojan": _parse_trojan,
    "hysteria2": _parse_hysteria2,
    "hy2": _parse_hysteria2,
    "tuic": _parse_tuic,
}


def parse_uri(uri: str) -> Dict[str, Any]:
    """Определить схему и распарсить ссылку. Кидает ``ParseError``."""
    if not uri or not isinstance(uri, str):
        raise ParseError("пустая ссылка")
    s = uri.strip()
    low = s.lower()
    scheme = low.split("://", 1)[0] if "://" in low else ""
    parser = _SCHEME_PARSERS.get(scheme)
    if parser is None:
        raise ParseError(f"неподдерживаемая схема: {scheme!r}")
    return parser(s)


# ─────────────────────────────────────────────────────────────────────────────
#  Подписки (http:// / https://) — список серверов для выбора локации
# ─────────────────────────────────────────────────────────────────────────────
# Многие сервисы подписок (и CDN перед ними, напр. cdn.mitelis.net) отдают
# конфиг ТОЛЬКО известным VPN-клиентам, а незнакомый/пустой User-Agent режут
# заглушкой HTTP 403. Поэтому представляемся цепочкой популярных клиентов —
# v2rayNG первым: он возвращает base64-список ссылок, который наш парсер
# понимает. clash-клиенты часто отдают YAML (мы его не читаем), браузерный UA
# у части сервисов уводит в бесконечный редирект — их не используем как основные.
_SUB_USER_AGENTS = (
    "v2rayNG/1.8.19",
    "sing-box/1.9.0",
    "Clash/2023.08.17",
    "clash.meta/1.16.0",
    "EXDPI/1.0 (sing-box subscription client)",
)
# обратная совместимость (константа могла использоваться в других местах)
_SUB_USER_AGENT = _SUB_USER_AGENTS[0]


def _sub_http_get(url: str, timeout: float, user_agent: str) -> bytes:
    headers = {"User-Agent": user_agent, "Accept": "*/*"}
    # HWID устройства: панели с привязкой к устройству (Remnawave и т.п.)
    # без него отдают заглушку «App not supported / Please use Happ».
    try:
        headers.update(hwid.device_headers())
    except Exception:
        log.warning("не удалось добавить HWID-заголовки", exc_info=True)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ─────────────────────────────────────────────────────────────────────────────
#  Xray-JSON подписки (панели с HWID-привязкой)
# ─────────────────────────────────────────────────────────────────────────────
# Панели Remnawave и подобные при передаче HWID отдают не base64-список ссылок,
# а полноценный Xray-конфиг (или список конфигов) с proxy-outbound-ами. Достаём
# из каждого outbound адрес/uuid/транспорт и собираем обратно vless://-ссылку,
# которую понимает parse_uri(). Служебные outbound-ы (direct/block/dns) и
# дубликаты пропускаем.
def _xray_stream_params(ss):
    """streamSettings Xray → query-параметры URI (совместимо с _parse_vless)."""
    params = {}
    network = (ss.get("network") or "tcp").lower()
    params["type"] = network
    security = (ss.get("security") or "").lower()
    if security:
        params["security"] = security

    tls = ss.get("tlsSettings") or ss.get("realitySettings") or {}
    sni = tls.get("serverName") or ""
    if sni:
        params["sni"] = sni
    fp = tls.get("fingerprint") or ""
    if fp:
        params["fp"] = fp
    alpn = tls.get("alpn")
    if alpn:
        params["alpn"] = ",".join(alpn) if isinstance(alpn, list) else str(alpn)
    if security == "reality":
        if tls.get("publicKey"):
            params["pbk"] = tls["publicKey"]
        if tls.get("shortId"):
            params["sid"] = tls["shortId"]

    if network == "grpc":
        g = ss.get("grpcSettings") or {}
        if g.get("serviceName"):
            params["serviceName"] = g["serviceName"]
    elif network == "ws":
        w = ss.get("wsSettings") or {}
        if w.get("path"):
            params["path"] = w["path"]
        host = (w.get("headers") or {}).get("Host") or ""
        if host:
            params["host"] = host
    elif network in ("http", "h2", "httpupgrade", "xhttp", "splithttp"):
        h = ss.get("httpSettings") or ss.get("xhttpSettings") or {}
        if h.get("path"):
            params["path"] = h["path"]
        hosts = h.get("host")
        if hosts:
            params["host"] = hosts[0] if isinstance(hosts, list) else str(hosts)
    return params


def _xray_outbound_to_uri(ob, name=""):
    """Один Xray-outbound → URI или "".

    ``name`` — человекочитаемое имя локации (из ``remarks`` конфига); если
    задано, идёт во фрагмент ссылки (``#name``) и становится подписью сервера
    в UI. Иначе во фрагмент кладём хост.
    """
    proto = (ob.get("protocol") or "").lower()
    settings = ob.get("settings") or {}
    ss = ob.get("streamSettings") or {}
    params = _xray_stream_params(ss)

    def _frag(addr):
        return urllib.parse.quote(str(name) if name else str(addr))

    if proto == "vless":
        vnext = settings.get("vnext") or []
        if not vnext:
            return ""
        node = vnext[0]
        users = node.get("users") or [{}]
        user = users[0]
        addr = node.get("address") or ""
        port = node.get("port") or 0
        uid = user.get("id") or ""
        if not (addr and port and uid):
            return ""
        if user.get("flow"):
            params["flow"] = user["flow"]
        params.setdefault("encryption", user.get("encryption") or "none")
        query = urllib.parse.urlencode(params)
        return "vless://" + str(uid) + "@" + str(addr) + ":" + str(port) + "?" + query + "#" + _frag(addr)

    if proto == "vmess":
        vnext = settings.get("vnext") or []
        if not vnext:
            return ""
        node = vnext[0]
        users = node.get("users") or [{}]
        user = users[0]
        addr = node.get("address") or ""
        port = node.get("port") or 0
        uid = user.get("id") or ""
        if not (addr and port and uid):
            return ""
        vm = {
            "v": "2", "ps": str(name) if name else str(addr), "add": str(addr),
            "port": str(port), "id": str(uid), "aid": str(user.get("alterId", 0)),
            "net": params.get("type", "tcp"), "type": "none",
            "host": params.get("host", ""), "path": params.get("path", ""),
            "tls": params.get("security", ""), "sni": params.get("sni", ""),
        }
        raw = base64.b64encode(json.dumps(vm).encode("utf-8")).decode("ascii")
        return "vmess://" + raw

    if proto == "trojan":
        servers = settings.get("servers") or []
        if not servers:
            return ""
        node = servers[0]
        addr = node.get("address") or ""
        port = node.get("port") or 0
        pwd = node.get("password") or ""
        if not (addr and port and pwd):
            return ""
        query = urllib.parse.urlencode(params)
        return "trojan://" + urllib.parse.quote(str(pwd)) + "@" + str(addr) + ":" + str(port) + "?" + query + "#" + _frag(addr)

    if proto == "shadowsocks":
        servers = settings.get("servers") or []
        if not servers:
            return ""
        node = servers[0]
        addr = node.get("address") or ""
        port = node.get("port") or 0
        method = node.get("method") or ""
        pwd = node.get("password") or ""
        if not (addr and port and method):
            return ""
        userinfo = base64.urlsafe_b64encode((str(method) + ":" + str(pwd)).encode("utf-8")).decode("ascii").rstrip("=")
        return "ss://" + userinfo + "@" + str(addr) + ":" + str(port) + "#" + _frag(addr)

    if proto in ("hysteria2", "hysteria"):
        # Xray hysteria2: settings.address/port + streamSettings.hysteriaSettings.auth
        addr = settings.get("address") or ""
        port = settings.get("port") or 0
        hy = ss.get("hysteriaSettings") or {}
        pwd = hy.get("auth") or settings.get("auth") or settings.get("password") or ""
        if not (addr and port):
            return ""
        tls = ss.get("tlsSettings") or {}
        q = {}
        sni = tls.get("serverName") or params.get("sni") or ""
        if sni:
            q["sni"] = sni
        if str(tls.get("allowInsecure") or "").lower() in ("1", "true"):
            q["insecure"] = "1"
        query = urllib.parse.urlencode(q)
        tail = ("?" + query) if query else ""
        return "hysteria2://" + urllib.parse.quote(str(pwd)) + "@" + str(addr) + ":" + str(port) + tail + "#" + _frag(addr)

    return ""


# Протоколы outbound-а, которые мы умеем превращать в ссылку
_XRAY_PROXY_PROTOS = ("vless", "vmess", "trojan", "shadowsocks", "hysteria2", "hysteria")


def _xray_primary_outbound(cfg):
    """Основной proxy-outbound конфига (tag == "proxy"), иначе первый
    поддерживаемый. Резервные proxy-2..proxy-N (для балансировки на стороне
    клиента) игнорируем — иначе одна локация раздувается в десятки серверов."""
    obs = [o for o in (cfg.get("outbounds") or []) if isinstance(o, dict)]
    supported = [o for o in obs if (o.get("protocol") or "").lower() in _XRAY_PROXY_PROTOS]
    if not supported:
        return None
    for o in supported:
        if o.get("tag") == "proxy":
            return o
    return supported[0]


def _xray_json_to_uris(body):
    """Xray-JSON (один конфиг или СПИСОК конфигов) → список URI-ссылок.

    Панель отдаёт по одному конфигу на локацию, и в каждом — основной сервер
    (tag "proxy") плюс запасные (proxy-2..proxy-N) для клиентской балансировки.
    Берём с каждого конфига ТОЛЬКО основной сервер и подписываем его именем
    локации из ``remarks`` (там флаг-эмодзи + страна). Так число серверов
    совпадает с числом локаций, а не раздувается запасными узлами.
    """
    try:
        data = json.loads(body)
    except Exception:
        return []
    configs = data if isinstance(data, list) else [data]
    uris = []
    seen = set()
    for cfg in configs:
        if not isinstance(cfg, dict):
            continue
        ob = _xray_primary_outbound(cfg)
        if ob is None:
            continue
        name = str(cfg.get("remarks") or cfg.get("name") or "").strip()
        try:
            uri = _xray_outbound_to_uri(ob, name=name)
        except Exception:
            uri = ""
        if not uri:
            continue
        key = uri.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        uris.append(uri)
    return uris


def is_subscription_url(s: str) -> bool:
    """``True``, если строка похожа на ссылку-подписку (http/https), а не
    на прямую ссылку подключения (vless/ss)."""
    if not s or not isinstance(s, str):
        return False
    low = s.strip().lower()
    return low.startswith("http://") or low.startswith("https://")


def fetch_subscription(url: str, timeout: float = 10.0) -> List[str]:
    """Скачать подписку и вернуть список ссылок (``vless://``/``ss://``).

    Тело подписки чаще всего — base64 от списка ссылок, разделённых
    переводом строки (стандарт V2Ray/sing-box), но многие панели (3x-ui,
    Marzban и т.п.) отдают тот же список ОТКРЫТЫМ текстом. base64.b64decode
    с ``validate=False`` "успешно" декодирует произвольный текст в мусорные
    байты вместо ошибки — поэтому сначала проверяем, не похож ли текст на
    список ссылок как есть, и только если нет — пробуем как base64.
    Некоторые сервера подписок капризны к заголовкам/HTTP-версии — ставим
    обычный браузерный ``User-Agent``.
    """
    # перебираем клиентские User-Agent: сервис может резать одни и пускать другие
    raw = None
    last_http_err = None
    last_other_err = None
    for _ua in _SUB_USER_AGENTS:
        try:
            raw = _sub_http_get(url, timeout, _ua)
            break
        except urllib.error.HTTPError as exc:
            last_http_err = exc
            if exc.code in (401, 403):
                # доступ режется по клиенту — пробуем следующий UA
                continue
            # прочие HTTP-коды (404/5xx) сменой UA не лечатся
            raise ParseError(
                f"подписка недоступна: HTTP {exc.code} {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            last_other_err = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_other_err = exc
            continue

    if raw is None:
        if last_http_err is not None:
            hint = (
                " (сервер блокирует доступ для всех клиентов — проверьте, "
                "не истекла ли подписка и верна ли ссылка)"
                if last_http_err.code in (401, 403) else ""
            )
            raise ParseError(
                f"подписка недоступна: HTTP {last_http_err.code} "
                f"{last_http_err.reason}{hint}"
            ) from last_http_err
        if last_other_err is not None:
            reason = getattr(last_other_err, "reason", last_other_err)
            raise ParseError(f"не удалось скачать подписку: {reason}") from last_other_err
        raise ParseError("не удалось скачать подписку")

    body = raw.decode("utf-8", errors="ignore")
    schemes = tuple(f"{s}://" for s in _SCHEME_PARSERS)

    def _extract(text: str) -> List[str]:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return [ln for ln in lines if ln.lower().startswith(schemes)]

    links = _extract(body)
    if not links:
        # не похоже на открытый текст — пробуем как base64 (стандарт подписок)
        try:
            decoded = _b64decode_loose(body)
            links = _extract(decoded.decode("utf-8", errors="ignore"))
        except Exception:
            links = []

    if not links:
        # панели с HWID-привязкой отдают Xray-JSON вместо списка ссылок —
        # конвертируем его outbound-ы обратно в vless://-ссылки
        stripped = body.lstrip()
        if stripped[:1] in ("[", "{"):
            links = _xray_json_to_uris(body)

    if not links:
        raise ParseError(
            "подписка не содержит поддерживаемых ссылок "
            "(vless/ss/vmess/trojan/hysteria2/tuic)"
        )
    return links


def list_servers(uri_or_sub: str) -> List[Dict[str, Any]]:
    """Вернуть список серверов
    ``[{"tag", "uri", "type", "server", "server_port"}, ...]``.

    Если передана прямая ссылка (``vless://``/``ss://``/...) — список из
    одного элемента. Если передана подписка (``http://``/``https://``) —
    качаем и парсим каждую ссылку; невалидные строки внутри подписки
    пропускаем (не должна одна плохая ссылка ронять всю подписку), но если
    валидных серверов не осталось — кидаем ``ParseError``.

    ``server``/``server_port`` в результате нужны UI для замера пинга
    (см. ``app.dpi_test``), без повторного парсинга URI.
    """
    s = (uri_or_sub or "").strip()
    if not s:
        raise ParseError("пустая ссылка")

    if is_subscription_url(s):
        links = fetch_subscription(s)
    else:
        links = [s]

    servers: List[Dict[str, Any]] = []
    seen_tags: Dict[str, int] = {}
    for link in links:
        try:
            parsed = parse_uri(link)
        except ParseError:
            continue
        tag = str(parsed.get("tag") or "server")
        n = seen_tags.get(tag, 0)
        seen_tags[tag] = n + 1
        if n:
            tag = f"{tag} ({n + 1})"
        servers.append({
            "tag": tag,
            "uri": link,
            "type": parsed.get("type", ""),
            "server": parsed.get("server", ""),
            "server_port": parsed.get("server_port", 0),
        })

    if not servers:
        raise ParseError("не удалось разобрать ни одного сервера")
    return servers


def ping_server(host: str, port: int, timeout: float = 3.0) -> int:
    """TCP-connect задержка до ``host:port`` в миллисекундах.

    Не устанавливает VPN/TLS-сессию — просто открывает и сразу закрывает
    TCP-сокет, как это делают Happ/v2rayTun при показе "пинга" в списке
    локаций. Возвращает ``-1``, если сервер недоступен за ``timeout``.
    """
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError:
        return -1
    return int((time.monotonic() - start) * 1000)


# Код страны/название → ISO 3166-1 alpha-2. По тегу сервера в подписке
# (обычно там уже либо флаг-эмодзи, либо название/код страны — расшифровку
# по IP делать не нужно, а онлайн geo-IP лукап сам может быть недоступен
# из-за DPI). Возвращаем код, а не готовый эмодзи-флаг: у Windows/Tk нет
# надёжного рендера региональных-индикаторных эмодзи (шрифт Segoe UI
# рисует их как два обычных letter-glyph'а вместо флага) — сам флаг рисуем
# на Canvas в ``widgets.ServerListBox`` по этому коду.
_COUNTRY_CODES: Dict[str, str] = countries.COUNTRY_CODES

# Региональные буквы A-Z в виде Unicode Regional Indicator Symbols
# (U+1F1E6..U+1F1FF), из которых состоят флаг-эмодзи — нужно и для их
# обнаружения в тегах, и для перевода индикатора обратно в букву кода.
_REGIONAL_A = 0x1F1E6


def _flag_emoji_to_code(pair: str) -> str:
    return "".join(chr(ord(ch) - _REGIONAL_A + ord("A")) for ch in pair)


def guess_country_code(tag: str) -> str:
    """ISO-код страны (``"DE"``, ``"RU"``, ...) по тегу сервера, либо ``""``.

    Сначала ищем флаг-эмодзи прямо в теге (там уже зашит код страны — просто
    декодируем пару региональных индикаторов обратно в буквы), иначе ищем
    код/название страны как отдельное "слово".
    """
    if not tag:
        return ""
    for i, ch in enumerate(tag):
        if "\U0001F1E6" <= ch <= "\U0001F1FF" and i + 1 < len(tag):
            nxt = tag[i + 1]
            if "\U0001F1E6" <= nxt <= "\U0001F1FF":
                return _flag_emoji_to_code(ch + nxt)
    import re
    words = re.findall(r"[A-ZА-Я]+", tag.upper())
    for w in words:
        if w in _COUNTRY_CODES:
            return _COUNTRY_CODES[w]
    return ""


def clean_tag(tag: str) -> str:
    """Тег без встроенных флаг-эмодзи (их всё равно рисуем сами на Canvas,
    оставлять текстовые огрызки региональных индикаторов в подписи не надо)."""
    if not tag:
        return tag
    out = []
    i = 0
    while i < len(tag):
        ch = tag[i]
        if "\U0001F1E6" <= ch <= "\U0001F1FF" and i + 1 < len(tag) and (
            "\U0001F1E6" <= tag[i + 1] <= "\U0001F1FF"
        ):
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Сборка блоков sing-box-конфига
# ─────────────────────────────────────────────────────────────────────────────
def _outbound_from_parsed(p: Dict[str, Any]) -> Dict[str, Any]:
    """Распарсенный словарь → outbound-блок sing-box."""
    ptype = p["type"]

    if ptype in ("vless", "vmess"):
        ob: Dict[str, Any] = {
            "type": ptype,
            "tag": p["tag"],
            "server": p["server"],
            "server_port": p["server_port"],
            "uuid": p["uuid"],
        }
        if ptype == "vmess":
            ob["security"] = p.get("security", "auto")
            ob["alter_id"] = p.get("alter_id", 0)
        if p.get("flow"):
            ob["flow"] = p["flow"]
        if p.get("tls"):
            ob["tls"] = p["tls"]
        if p.get("transport"):
            ob["transport"] = p["transport"]
        return ob

    if ptype == "shadowsocks":
        return {
            "type": "shadowsocks",
            "tag": p["tag"],
            "server": p["server"],
            "server_port": p["server_port"],
            "method": p["method"],
            "password": p["password"],
        }

    if ptype == "trojan":
        ob = {
            "type": "trojan",
            "tag": p["tag"],
            "server": p["server"],
            "server_port": p["server_port"],
            "password": p["password"],
        }
        if p.get("tls"):
            ob["tls"] = p["tls"]
        if p.get("transport"):
            ob["transport"] = p["transport"]
        return ob

    if ptype == "hysteria2":
        ob = {
            "type": "hysteria2",
            "tag": p["tag"],
            "server": p["server"],
            "server_port": p["server_port"],
            "password": p["password"],
        }
        if p.get("obfs"):
            ob["obfs"] = p["obfs"]
        if p.get("tls"):
            ob["tls"] = p["tls"]
        return ob

    if ptype == "tuic":
        return {
            "type": "tuic",
            "tag": p["tag"],
            "server": p["server"],
            "server_port": p["server_port"],
            "uuid": p["uuid"],
            "password": p["password"],
            "congestion_control": p.get("congestion_control", "bbr"),
            "tls": p.get("tls", {}),
        }

    raise ParseError(f"неизвестный тип outbound: {ptype!r}")


_DNS_SERVERS = {
    "cloudflare": "1.1.1.1",
    "google": "8.8.8.8",
    "quad9": "9.9.9.9",
    "adguard": "94.140.14.14",
}

# VPN-настройки текущей сборки конфига. Заполняется в build_config() из
# переданного cfg — функции _build_* читают отсюда (не таскаем аргумент через
# всю цепочку). Дефолты безопасны, если options не передали.
_CURRENT_OPTS: Dict[str, Any] = {}


def _vpn_options(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Нормализовать VPN-настройки из cfg в набор опций сборки конфига."""
    cfg = cfg or {}
    stack = str(cfg.get("vpn_tun_stack", "mixed"))
    if stack not in ("mixed", "gvisor", "system"):
        stack = "mixed"
    try:
        mtu = int(cfg.get("vpn_mtu", 1500))
    except (TypeError, ValueError):
        mtu = 1500
    if not (576 <= mtu <= 9000):
        mtu = 1500
    dns = str(cfg.get("vpn_dns", "cloudflare"))
    return {
        "dns_server": _DNS_SERVERS.get(dns, "1.1.1.1"),
        "stack": stack,
        "mtu": mtu,
        "ipv6": bool(cfg.get("vpn_ipv6", False)),
        "strict_route": bool(cfg.get("vpn_strict_route", False)),
        "block_quic": bool(cfg.get("vpn_block_quic", False)),
        "ru_direct": bool(cfg.get("vpn_ru_direct", True)),
    }


def _build_inbounds() -> List[Dict[str, Any]]:
    """TUN-inbound: перехватывает весь трафик Windows.

    Значения — из ``_CURRENT_OPTS`` (VPN-настройки пользователя) с безопасными
    дефолтами. Что изменилось против первой версии (это и убивало интернет):
      * mtu 9000 -> 1500 (по умолчанию). Jumbo-MTU поверх обычного линка даёт
        фрагментацию/чёрные дыры — крупные пакеты молча теряются, соединения
        «висят». 1500 безопасен. (пользователь может поднять в настройках)
      * strict_route True -> False (по умолчанию). strict_route на Windows
        часто рубит ВЕСЬ трафик; включается осознанно как «kill-switch».
      * stack "gvisor" -> "mixed" по умолчанию (быстрее gvisor, стабильнее
        system).
    sing-box >= 1.13: адрес TUN — список CIDR (``address``), сниффинг вынесен
    в ``route.rules`` (см. ``_build_route``).
    """
    opts = _CURRENT_OPTS
    address = ["172.19.0.1/30"]
    if opts.get("ipv6"):
        address.append("fdfe:dcba:9876::1/126")
    return [{
        "type": "tun",
        "tag": "tun-in",
        "interface_name": "EXDPI-Tun",
        "address": address,
        "mtu": int(opts.get("mtu", 1500)),
        "auto_route": True,
        "strict_route": bool(opts.get("strict_route", False)),
        "stack": str(opts.get("stack", "mixed")),
    }]


def _build_dns(out_tag: str) -> Dict[str, Any]:
    """DNS без утечек (sing-box >= 1.12, type-based servers).

    ``dns-remote`` резолвит через туннель (``detour`` = прокси-outbound),
    ``dns-direct`` — напрямую, минуя прокси.

    КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: домен самого прокси-сервера обязан резолвиться
    ``dns-direct``-ом. Иначе — циклический тупик: чтобы поднять туннель,
    sing-box должен зайти на прокси по имени, а имя резолвится только через
    ещё-не-поднятый туннель → tunnel не встаёт → TUN ``final`` становится
    чёрной дырой → интернет пропадает целиком. Поэтому
    ``route.default_domain_resolver = "dns-direct"`` (см. ``_build_route``).

    ``strategy`` = ``ipv4_only`` (или ``prefer_ipv4`` при включённом IPv6),
    иначе IPv6-запросы могут выйти мимо TUN.
    """
    opts = _CURRENT_OPTS
    server = str(opts.get("dns_server", "1.1.1.1"))
    dns: Dict[str, Any] = {
        "servers": [
            {"tag": "dns-remote", "type": "https", "server": server, "detour": out_tag},
            {"tag": "dns-direct", "type": "https", "server": server},
        ],
        "rules": [],
        "strategy": "prefer_ipv4" if opts.get("ipv6") else "ipv4_only",
    }
    if opts.get("ru_direct", True):
        # .ru/.su/.рф — резолвим напрямую (быстрее, не гоняем через прокси).
        dns["rules"].append({
            "domain_suffix": [".ru", ".su", ".xn--p1ai"],
            "server": "dns-direct",
        })
    return dns


def _build_route(out_tag: str) -> Dict[str, Any]:
    """Маршрутизация. ``auto_detect_interface`` важен на Windows.

    ``default_domain_resolver = "dns-direct"`` — тот самый фикс тупика резолва
    прокси-домена (см. ``_build_dns``). ``hijack-dns`` перехватывает системные
    DNS-запросы в TUN (иначе часть уходит мимо и ловит подмену DPI).
    """
    opts = _CURRENT_OPTS
    rules: List[Dict[str, Any]] = [
        {"action": "sniff"},
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_is_private": True, "outbound": "direct"},
    ]
    if opts.get("ru_direct", True):
        rules.append({"domain_suffix": [".ru", ".su", ".xn--p1ai"], "outbound": "direct"})
    if opts.get("block_quic"):
        # QUIC (UDP/443) режем → браузер откатывается на TCP/TLS. Часто чинит
        # «сайт открылся, видео/стрим не идёт» под VPN.
        rules.append({"protocol": "quic", "action": "reject"})
    return {
        "rules": rules,
        "auto_detect_interface": True,
        "default_domain_resolver": "dns-direct",
        "final": out_tag,
    }


def build_config(uri: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Из ссылки → полный конфиг Sing-box (dict). Кидает ``ParseError``.

    ``options`` — cfg приложения (VPN-настройки): влияют на MTU, сетевой стек,
    DNS-провайдер, kill-switch (strict_route), обход .ru напрямую и блокировку
    QUIC.

    Отличие от старой версии: убран служебный outbound ``{"type":"block"}`` —
    тип outbound "block" удалён в sing-box 1.13 (в бандле 1.13.14) и ломает
    парсинг. На него всё равно никто не ссылался.
    """
    global _CURRENT_OPTS
    _CURRENT_OPTS = _vpn_options(options)
    parsed = parse_uri(uri)
    out_tag = parsed["tag"]

    config: Dict[str, Any] = {
        "log": {"level": "info", "timestamp": True},
        "dns": _build_dns(out_tag),
        "inbounds": _build_inbounds(),
        "outbounds": [
            _outbound_from_parsed(parsed),
            {"type": "direct", "tag": "direct"},
        ],
        "route": _build_route(out_tag),
    }
    return config


# ─────────────────────────────────────────────────────────────────────────────
#  Запись на диск
# ─────────────────────────────────────────────────────────────────────────────
def save_config(uri: str, path: Optional[Path] = None,
                options: Optional[Dict[str, Any]] = None) -> Path:
    """Сгенерировать конфиг из ссылки и сохранить как singbox_config.json.

    По умолчанию пишется в ``%APPDATA%/EXDPI/singbox_config.json`` (см.
    ``paths.singbox_config_path``). Возвращает Path к записанному файлу.
    """
    target = Path(path) if path is not None else paths.singbox_config_path()
    config = build_config(uri, options)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fp:
        json.dump(config, fp, indent=2, ensure_ascii=False)
    log.info("singbox config saved: %s (outbound=%s)", target, parse_uri(uri)["tag"])
    return target


# ─────────────────────────────────────────────────────────────────────────────
#  Лёгкая самопроверка для ручного теста: python -m app.singbox_config <link>
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":  # pragma: no cover
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("usage: python -m app.singbox_config <vless://... | ss://...>")
        raise SystemExit(2)
    try:
        cfg = build_config(sys.argv[1])
    except ParseError as exc:
        print(f"PARSE ERROR: {exc}")
        raise SystemExit(1)
    print(json.dumps(cfg, indent=2, ensure_ascii=False))
