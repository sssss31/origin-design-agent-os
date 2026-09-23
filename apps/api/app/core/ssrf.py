"""Outbound URL guard for custom REST integrations (spec §17: SSRF protection + allowlist).

Rules: https only (http allowed outside production when OUTBOUND_ALLOW_HTTP=true), no
userinfo, no private/loopback/link-local/metadata addresses after DNS resolution, optional
host allowlist (exact host or subdomain), redirects are never followed by callers.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

from app.core.config import Settings

Resolver = Callable[[str], list[str]]
BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "instance-data"}


class OutboundBlocked(ValueError):
    pass


def resolve_host(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise OutboundBlocked(f"host {host!r} does not resolve") from exc
    return sorted({str(info[4][0]) for info in infos})


def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _is_public(str(addr.ipv4_mapped))
    return True


def host_allowed(host: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    h = host.lower()
    return any(h == a or h.endswith("." + a) for a in (x.lower().strip() for x in allowlist if x.strip()))


def validate_outbound_url(url: str, settings: Settings, *, resolver: Resolver | None = None) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme == "http" and not settings.outbound_allow_http:
        raise OutboundBlocked("only https endpoints are allowed")
    if scheme not in ("http", "https"):
        raise OutboundBlocked(f"unsupported scheme {scheme!r}")
    if parts.username or parts.password:
        raise OutboundBlocked("credentials in the URL are not allowed; use a secret reference")
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise OutboundBlocked("URL has no host")
    if host in BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".internal"):
        raise OutboundBlocked(f"host {host!r} is not allowed")
    if not host_allowed(host, settings.outbound_allowed_hosts_list):
        raise OutboundBlocked(f"host {host!r} is not in OUTBOUND_ALLOWED_HOSTS")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = (resolver or resolve_host)(host)  # looked up at call time so tests can stub DNS
    for ip in addresses:
        if not _is_public(ip):
            raise OutboundBlocked(f"host {host!r} resolves to a non-public address")
    return host
