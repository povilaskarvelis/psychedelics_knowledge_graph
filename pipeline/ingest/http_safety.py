"""Small outbound-HTTP safety helpers for provider and PDF retrieval."""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


DEFAULT_MAX_RESPONSE_BYTES = 128 * 1024 * 1024


class UnsafeOutboundUrl(ValueError):
    """Raised when an outbound URL could reach a non-public network target."""


class ResponseTooLarge(RuntimeError):
    """Raised before an oversized response is retained in memory or on disk."""


def _public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global


def validate_public_http_url(
    url: str,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    """Require HTTP(S) and reject hosts resolving outside the public Internet."""
    value = str(url or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeOutboundUrl("Only http and https outbound URLs are allowed")
    if not parsed.hostname:
        raise UnsafeOutboundUrl("Outbound URL is missing a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeOutboundUrl("Outbound URLs must not contain credentials")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeOutboundUrl(f"Outbound URL host is not public: {hostname}")

    try:
        literal = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        try:
            records = resolver(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise URLError(f"Could not resolve outbound URL host: {hostname}") from exc
        addresses = {record[4][0] for record in records if record[4]}
        if not addresses:
            raise URLError(f"Could not resolve outbound URL host: {hostname}")
        if any(not _public_ip(address) for address in addresses):
            raise UnsafeOutboundUrl(
                f"Outbound URL host resolves to a non-public address: {hostname}"
            )
    else:
        if not _public_ip(str(literal)):
            raise UnsafeOutboundUrl(f"Outbound URL address is not public: {literal}")
    return value


def read_bounded_response(
    response, max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
) -> bytes:
    """Read at most ``max_bytes`` from an urllib-style response."""
    maximum = max(1, int(max_bytes))
    raw_length = response.headers.get("Content-Length") if response.headers else None
    if raw_length:
        try:
            declared_length = int(raw_length)
        except (TypeError, ValueError):
            declared_length = 0
        if declared_length > maximum:
            raise ResponseTooLarge(
                f"Response declares {declared_length} bytes; limit is {maximum} bytes"
            )
    body = response.read(maximum + 1)
    if len(body) > maximum:
        raise ResponseTooLarge(f"Response exceeded the {maximum}-byte limit")
    return body


class PublicHttpRedirectHandler(HTTPRedirectHandler):
    """Validate each redirect before urllib connects to the next destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        validate_public_http_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def build_public_http_opener():
    return build_opener(PublicHttpRedirectHandler())
