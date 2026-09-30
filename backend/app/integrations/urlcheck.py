"""URL hygiene shared by the IFS and Graph clients (SSRF / credential-leak guards).

Always enforced: scheme must be http or https, a host is required, no userinfo (``user:pw@host``),
no secret-looking query parameters (``?apikey=...``), no control characters.

Enforced unless ``allow_private_hosts`` is true: the host must not resolve to a loopback, private
(RFC 1918 / ULA), link-local (incl. the 169.254.169.254 cloud-metadata address), multicast,
reserved or unspecified address. Default is **false**. On-prem IFS normally lives on a private
network, so an administrator sets ``allow_private_hosts: true`` on that connector explicitly.

Limits: the check resolves the name at call time, so a DNS-rebinding attacker who controls the
zone could still change the answer between check and connect; keep egress firewalling in place.
A host name that does not resolve is not rejected here (the connection will fail anyway).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlsplit

from .redact import is_secret_key

_CTRL = re.compile(r"[\x00-\x20\x7f]")


class UnsafeUrlError(ValueError):
    """The URL is not acceptable (message never contains credentials)."""


def _blocked(ip: ipaddress._BaseAddress) -> bool:
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped
                                         and _blocked(ip.ipv4_mapped)))


def check_url(url: str, what: str = "URL", *, allow_private_hosts: bool = False) -> str:
    u = str(url).strip()
    if not u or _CTRL.search(u):
        raise UnsafeUrlError(f"{what}: empty or contains control characters/spaces")
    parts = urlsplit(u)
    if parts.scheme.lower() not in ("http", "https"):
        raise UnsafeUrlError(f"{what}: only http:// and https:// are allowed")
    if not parts.hostname:
        raise UnsafeUrlError(f"{what}: no host")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError(f"{what}: credentials must not be embedded in the URL")
    for k, _ in parse_qsl(parts.query, keep_blank_values=True):
        if is_secret_key(k):
            raise UnsafeUrlError(f"{what}: secrets must not be passed in the query string")
    if not allow_private_hosts:
        host = parts.hostname
        try:
            literal = ipaddress.ip_address(host)
            addrs = [literal]
        except ValueError:
            try:
                infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80),
                                           type=socket.SOCK_STREAM)
            except OSError:
                return u
            addrs = [ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos]
        if any(_blocked(a) for a in addrs):
            raise UnsafeUrlError(f"{what}: host resolves to a private/loopback/link-local address; "
                                 f"set allow_private_hosts=true only if this is an intended on-prem target")
    return u
