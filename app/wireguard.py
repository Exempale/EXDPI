"""WireGuard и AmneziaWG для VPN-режима (появилось в 3.0).

Что понимаем:
  * обычные wg-quick ``.conf``-файлы (импорт из файла в VPN-режиме);
  * AmneziaWG ``.conf`` — тот же формат плюс параметры обфускации
    (Jc/Jmin/Jmax/S1/S2/H1..H4);
  * ссылки ``wireguard://`` и ``wg://`` (формат v2rayN/NekoBox:
    ``wireguard://<pubkey>@host:port?private_key=...&address=...``).

Amnezia-ссылки вида ``vpn://…`` (base64-JSON AmneziaVPN) не поддерживаются —
просьте конфиг ``.conf``: Amnezia умеет его экспортировать.

Результат парсинга — словарь ``wg``; из него ``endpoint_config`` собирает
секцию ``endpoints`` для sing-box >= 1.11 (wireguard-outbound устарел).
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qsl, unquote

log = logging.getLogger("dpibypass.wireguard")

AWG_KEYS = ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4")
_AWG_CONF_NAMES = {
    "jc": "jc", "jmin": "jmin", "jmax": "jmax", "s1": "s1", "s2": "s2",
    "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4",
}


class WireguardError(ValueError):
    pass


# Поддерживает ли движок обфускацию AmneziaWG (поле "amnezia" в peer).
# sing-box 1.13.14 (бандл) её НЕ знает — проверено `sing-box check`:
# "unknown field \"amnezia\"". Конфиги AWG при этом читаются, но подключение
# идёт как обычный WireGuard (на чисто-AWG сервере handshake не пройдёт).
# Переключить в True после обновления ядра на сборку с поддержкой AWG.
SUPPORTS_AWG = False


def _b64key(value: str, field: str) -> str:
    """Проверить, что значение похоже на base64-ключ (32 байта)."""
    v = (value or "").strip()
    try:
        raw = base64.b64decode(v + "=" * (-len(v) % 4), validate=True)
    except Exception:
        raise WireguardError(f"{field}: не base64-ключ")
    if len(raw) != 32:
        raise WireguardError(f"{field}: ключ должен быть 32 байта, получено {len(raw)}")
    return v


def _parse_address_list(value: str) -> List[str]:
    out = []
    for part in re.split(r"[,;]", str(value or "")):
        part = part.strip()
        if not part:
            continue
        if "/" not in part:
            # голый IP → приводим к CIDR, sing-box требует префикс
            part += "/32" if ":" not in part else "/128"
        out.append(part)
    return out


def _parse_reserved(value: str) -> Optional[List[int]]:
    v = (value or "").strip()
    if not v:
        return None
    if "," in v:  # формат "1,2,3"
        try:
            return [int(x) for x in v.split(",")]
        except ValueError:
            return None
    try:  # формат base64 из 3 байт
        raw = base64.b64decode(v + "=" * (-len(v) % 4))
        if len(raw) == 3:
            return list(raw)
    except Exception:
        pass
    return None


def _blank() -> Dict[str, Any]:
    return {
        "name": "",
        "private_key": "",
        "peer_public_key": "",
        "pre_shared_key": "",
        "endpoint_host": "",
        "endpoint_port": 51820,
        "local_address": [],
        "dns": [],
        "mtu": 0,           # 0 → берётся из VPN-настроек приложения
        "listen_port": 0,
        "keepalive": 0,
        "reserved": None,
        "awg": None,
    }


# ── .conf (wg-quick / AmneziaWG) ─────────────────────────────────────────────
def parse_wireguard_conf(text: str) -> Dict[str, Any]:
    """Разобрать содержимое .conf. Кидает WireguardError при мусоре."""
    wg = _blank()
    section = ""
    seen: Dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().lower()
        val = val.strip()
        if section == "interface":
            seen[key] = val
            if key == "privatekey":
                wg["private_key"] = val
            elif key == "address":
                wg["local_address"] = _parse_address_list(val)
            elif key == "dns":
                wg["dns"] = [d.strip() for d in re.split(r"[,;]", val) if d.strip()]
            elif key == "mtu":
                try:
                    wg["mtu"] = int(val)
                except ValueError:
                    pass
            elif key == "listenport":
                try:
                    wg["listen_port"] = int(val)
                except ValueError:
                    pass
            elif key in _AWG_CONF_NAMES:
                # AmneziaWG кладёт параметры обфускации в [Interface]
                awg = wg["awg"] or {}
                try:
                    awg[key] = int(val)
                except ValueError:
                    continue
                wg["awg"] = awg
        elif section == "peer":
            seen[key] = val
            if key == "publickey":
                wg["peer_public_key"] = val
            elif key == "presharedkey":
                wg["pre_shared_key"] = val
            elif key == "endpoint":
                host, port = _split_endpoint(val)
                wg["endpoint_host"], wg["endpoint_port"] = host, port
            elif key == "persistentkeepalive":
                try:
                    wg["keepalive"] = int(val)
                except ValueError:
                    pass
            elif key in _AWG_CONF_NAMES:
                awg = wg["awg"] or {}
                try:
                    awg[key] = int(val)
                except ValueError:
                    continue
                wg["awg"] = awg

    if not wg["private_key"]:
        raise WireguardError("в конфиге нет PrivateKey ([Interface])")
    if not wg["peer_public_key"]:
        raise WireguardError("в конфиге нет PublicKey ([Peer])")
    if not wg["endpoint_host"]:
        raise WireguardError("в конфиге нет Endpoint ([Peer])")
    wg["private_key"] = _b64key(wg["private_key"], "PrivateKey")
    wg["peer_public_key"] = _b64key(wg["peer_public_key"], "PublicKey")
    if wg["pre_shared_key"]:
        wg["pre_shared_key"] = _b64key(wg["pre_shared_key"], "PresharedKey")
    if not wg["local_address"]:
        # без адреса туннель поднимется, но роутить будет нечего — требуем
        raise WireguardError("в конфиге нет Address ([Interface])")
    return wg


def _split_endpoint(val: str) -> "tuple[str, int]":
    val = val.strip()
    if val.startswith("["):  # [ipv6]:port
        host, _, port = val.rpartition("]:")
        host = host.lstrip("[")
        try:
            return host, int(port)
        except ValueError:
            return host, 51820
    if ":" in val:
        host, _, port = val.rpartition(":")
        try:
            return host, int(port)
        except ValueError:
            return val, 51820
    return val, 51820


# ── wireguard:// / wg:// ─────────────────────────────────────────────────────
def parse_wireguard_uri(uri: str) -> Dict[str, Any]:
    """Разобрать ссылку формата v2rayN/NekoBox. Кидает WireguardError."""
    s = str(uri or "").strip()
    if "://" not in s:
        raise WireguardError("не похоже на wireguard:// ссылку")
    rest = s.split("://", 1)[1]
    if "@" not in rest:
        raise WireguardError("в ссылке нет публичного ключа пира")
    # pubkey в userinfo может быть стандартным base64 (со "/" и "+") —
    # urlparse такое режет по "/", поэтому отделяем его до парсинга
    userinfo, _, hostpart = rest.partition("@")
    p = urlparse("wg://" + hostpart)
    # ключи запроса пишут по-разному: private_key / privateKey / privatekey —
    # нормализуем к нижнему регистру без подчёркиваний
    q = {k.lower().replace("_", ""): v
         for k, v in parse_qsl(p.query, keep_blank_values=True)}
    # parse_qsl трактует "+" как пробел; в base64-ключах пробелов не бывает —
    # возвращаем "+" на место (продюсеры ссылок часто не экранируют)
    for _k in ("privatekey", "presharedkey"):
        if _k in q and " " in q[_k]:
            q[_k] = q[_k].replace(" ", "+")

    wg = _blank()
    wg["name"] = unquote(p.fragment or "").strip()
    wg["peer_public_key"] = unquote(userinfo).strip()
    wg["endpoint_host"] = p.hostname or ""
    wg["endpoint_port"] = p.port or 51820
    wg["private_key"] = q.get("privatekey") or ""
    wg["pre_shared_key"] = q.get("presharedkey") or ""
    wg["local_address"] = _parse_address_list(q.get("address", ""))
    if q.get("dns"):
        wg["dns"] = [d.strip() for d in re.split(r"[,;]", q["dns"]) if d.strip()]
    try:
        wg["mtu"] = int(q.get("mtu", 0) or 0)
    except ValueError:
        wg["mtu"] = 0
    wg["reserved"] = _parse_reserved(q.get("reserved", ""))

    if not wg["peer_public_key"]:
        raise WireguardError("в ссылке нет публичного ключа пира")
    if not wg["endpoint_host"]:
        raise WireguardError("в ссылке нет адреса сервера")
    if not wg["private_key"]:
        raise WireguardError("в ссылке нет private_key")
    wg["private_key"] = _b64key(wg["private_key"], "private_key")
    wg["peer_public_key"] = _b64key(wg["peer_public_key"], "peer public key")
    if wg["pre_shared_key"]:
        wg["pre_shared_key"] = _b64key(wg["pre_shared_key"], "preshared_key")
    if not wg["local_address"]:
        wg["local_address"] = ["172.16.0.2/32", "fd00::2/128"]
    return wg


# ── сборка секции endpoints для sing-box ────────────────────────────────────
def endpoint_config(wg: Dict[str, Any], mtu_fallback: int = 1408) -> Dict[str, Any]:
    """Секция ``endpoints`` (sing-box >= 1.11) из разобранного ``wg``."""
    peer: Dict[str, Any] = {
        "address": wg["endpoint_host"],
        "port": int(wg["endpoint_port"] or 51820),
        "public_key": wg["peer_public_key"],
        "allowed_ips": ["0.0.0.0/0", "::/0"],
    }
    if wg.get("pre_shared_key"):
        peer["pre_shared_key"] = wg["pre_shared_key"]
    if wg.get("reserved"):
        peer["reserved"] = wg["reserved"]
    if wg.get("awg") and SUPPORTS_AWG:
        peer["amnezia"] = {k: int(wg["awg"][k]) for k in AWG_KEYS if k in wg["awg"]}
    if wg.get("keepalive"):
        peer["persistent_keepalive_interval"] = int(wg["keepalive"])

    ep: Dict[str, Any] = {
        "type": "wireguard",
        "tag": "wg-out",
        "address": wg["local_address"],
        "private_key": wg["private_key"],
        "peers": [peer],
        "mtu": int(wg.get("mtu") or mtu_fallback),
    }
    if wg.get("listen_port"):
        ep["listen_port"] = int(wg["listen_port"])
    return ep


def summary(wg: Dict[str, Any]) -> str:
    """Короткая человекочитаемая строка (для UI/статуса)."""
    kind = "AmneziaWG" if wg.get("awg") else "WireGuard"
    return f"{kind} · {wg['endpoint_host']}:{wg['endpoint_port']}"
