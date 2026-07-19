from io import BytesIO
from urllib.error import URLError

import pytest

from pipeline.ingest.http_safety import (
    ResponseTooLarge,
    UnsafeOutboundUrl,
    read_bounded_response,
    validate_public_http_url,
)
from pipeline.ingest.metadata_utils import RateLimitedHttpClient


def resolver_for(*addresses: str):
    def resolve(_host, port, **_kwargs):
        return [(2, 1, 6, "", (address, port)) for address in addresses]

    return resolve


class FakeResponse(BytesIO):
    def __init__(self, body: bytes, content_length: str | None = None):
        super().__init__(body)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length


def test_public_http_url_accepts_public_dns_addresses() -> None:
    assert (
        validate_public_http_url(
            "https://publisher.example/paper.pdf",
            resolver=resolver_for(
                "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"
            ),
        )
        == "https://publisher.example/paper.pdf"
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost:8070/api/processFulltextDocument",
        "http://127.0.0.1/private",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/private",
        "https://user:password@example.org/private",
    ],
)
def test_public_http_url_rejects_unsafe_destinations(url: str) -> None:
    with pytest.raises(UnsafeOutboundUrl):
        validate_public_http_url(url)


def test_public_http_url_rejects_dns_names_with_any_private_answer() -> None:
    with pytest.raises(UnsafeOutboundUrl):
        validate_public_http_url(
            "https://publisher.example/paper.pdf",
            resolver=resolver_for("93.184.216.34", "10.0.0.5"),
        )


def test_shared_pipeline_client_rejects_non_http_urls_before_opening_them() -> None:
    client = RateLimitedHttpClient(rps=1000, max_retries=0)
    with pytest.raises(UnsafeOutboundUrl):
        client.get_bytes_once("file:///etc/passwd")


def test_public_http_url_reports_dns_failures_as_network_errors() -> None:
    def failing_resolver(*_args, **_kwargs):
        import socket

        raise socket.gaierror("not found")

    with pytest.raises(URLError):
        validate_public_http_url(
            "https://missing.example/paper.pdf", resolver=failing_resolver
        )


def test_bounded_response_rejects_declared_and_streamed_oversize_bodies() -> None:
    with pytest.raises(ResponseTooLarge):
        read_bounded_response(FakeResponse(b"small", "1000"), max_bytes=100)
    with pytest.raises(ResponseTooLarge):
        read_bounded_response(FakeResponse(b"x" * 101), max_bytes=100)
    assert read_bounded_response(FakeResponse(b"x" * 100), max_bytes=100) == b"x" * 100
