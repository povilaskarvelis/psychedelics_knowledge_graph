import hashlib
from pathlib import Path

from pipeline.fulltext.pdf_alternate_sources import (
    AlternatePdfCandidate,
    collect_alternate_pdf_candidates,
    dspace_original_content_links_from_json,
    extract_pdf_links,
    fetch_pdf_bytes_for_candidate,
    openalex_repository_candidates,
    semantic_scholar_candidates,
    solve_pmc_pow_cookie,
)


class FakeClient:
    def __init__(self, *, json_by_url=None, bytes_by_url=None):
        self.json_by_url = json_by_url or {}
        self.bytes_by_url = bytes_by_url or {}
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append(("json", url, params or {}, headers or {}))
        if url in self.json_by_url:
            return self.json_by_url[url]
        if params and params.get("ids") == "10.1000/example":
            return {"records": [{"doi": "10.1000/example", "pmcid": "PMC123"}]}
        raise RuntimeError(f"unexpected JSON URL: {url}")

    def get_bytes(self, url, headers=None):
        self.calls.append(("bytes", url, {}, headers or {}))
        value = self.bytes_by_url.get(url)
        if callable(value):
            return value(headers or {})
        if value is None:
            raise RuntimeError(f"unexpected bytes URL: {url}")
        return value


def pow_html(challenge: str, difficulty: int = 2) -> str:
    return f"""
    <script type="module">
      const POW_CHALLENGE = "{challenge}"
      const POW_DIFFICULTY = "{difficulty}"
      const POW_COOKIE_NAME = "cloudpmc-viewer-pow"
    </script>
    """


def test_solve_pmc_pow_cookie_finds_nonce_with_expected_prefix() -> None:
    challenge = "abc"

    cookie = solve_pmc_pow_cookie(pow_html(challenge, difficulty=2))

    name, value = cookie.split("=", 1)
    cookie_challenge, nonce = value.split(",", 1)
    digest = hashlib.sha256(f"{cookie_challenge}{nonce}".encode()).hexdigest()
    assert name == "cloudpmc-viewer-pow"
    assert cookie_challenge == challenge
    assert digest.startswith("00")


def test_fetch_pdf_bytes_for_candidate_solves_pmc_viewer_pow_cookie() -> None:
    url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/article.pdf"

    def response(headers):
        if "Cookie" in headers:
            return b"%PDF-1.7\nbody\n%%EOF\n"
        return pow_html("pmc-test", difficulty=2).encode()

    client = FakeClient(bytes_by_url={url: response})
    candidate = AlternatePdfCandidate(url=url, source="pmc")

    body, events, mode = fetch_pdf_bytes_for_candidate(client=client, candidate=candidate)

    assert body.startswith(b"%PDF-")
    assert mode == "pmc_pow"
    assert any(event["event"] == "pmc_pow_success" for event in events)
    assert any(call[3].get("Cookie", "").startswith("cloudpmc-viewer-pow=") for call in client.calls)


def test_extract_pdf_links_finds_esploro_download_url() -> None:
    html = '<a href="/view/pdfCoverPage?instCode=ABC&filePid=123&download=true">Download</a>'

    links = extract_pdf_links("https://repo.example/esploro/outputs/1", html)

    assert links == ["https://repo.example/view/pdfCoverPage?instCode=ABC&filePid=123&download=true"]


def test_fetch_pdf_bytes_for_candidate_follows_dspace_original_bitstream_api() -> None:
    landing_url = "https://repo.example/entities/publication/7743e827-8012-4cef-9bfa-e9567d67cb41"
    api_url = (
        "https://repo.example/server/api/core/bitstreams/search/showableByItem?"
        "uuid=7743e827-8012-4cef-9bfa-e9567d67cb41&name=ORIGINAL&embed=thumbnail&embed=format&page=0&size=10"
    )
    content_url = "https://repo.example/server/api/core/bitstreams/303e4943-8163-4f6f-a7ab-f4acaf7f2ba1/content"
    client = FakeClient(
        bytes_by_url={
            landing_url: b"<html><h1>Repository item</h1></html>",
            api_url: (
                b'{"_embedded":{"bitstreams":[{"uuid":"303e4943-8163-4f6f-a7ab-f4acaf7f2ba1",'
                b'"name":"article.pdf","_links":{"content":{"href":"'
                + content_url.encode()
                + b'"}}}]}}'
            ),
            content_url: b"%PDF-1.7\nbody\n%%EOF\n",
        }
    )
    candidate = AlternatePdfCandidate(url=landing_url, source="openalex")

    body, events, mode = fetch_pdf_bytes_for_candidate(client=client, candidate=candidate)

    assert body.startswith(b"%PDF-")
    assert mode == "dspace_bitstream_content"
    assert any(event["event"] == "dspace_bitstream_content_response" for event in events)


def test_dspace_original_content_links_from_json_rewrites_internal_host() -> None:
    payload = {
        "_embedded": {
            "bitstreams": [
                {
                    "uuid": "303e4943-8163-4f6f-a7ab-f4acaf7f2ba1",
                    "_links": {
                        "content": {
                            "href": "http://dd-ds2.ub.unibas.ch:8080/server/api/core/bitstreams/303e4943-8163-4f6f-a7ab-f4acaf7f2ba1/content"
                        }
                    },
                }
            ]
        }
    }

    links = dspace_original_content_links_from_json("https://edoc.unibas.ch/server/api/core/bitstreams/search/showableByItem", payload)

    assert links == [
        "https://edoc.unibas.ch/server/api/core/bitstreams/303e4943-8163-4f6f-a7ab-f4acaf7f2ba1/content"
    ]


def test_collect_alternate_pdf_candidates_uses_pmc_id_converter_and_article_page() -> None:
    article_url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"
    client = FakeClient(
        bytes_by_url={
            article_url: b'<html><meta name="citation_pdf_url" content="pdf/article.pdf"></html>',
        }
    )

    discovery = collect_alternate_pdf_candidates(
        client=client,
        task={"doi": "10.1000/example"},
        sources={"pmc"},
    )

    assert discovery["candidate_urls"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/article.pdf"
    assert discovery["candidates"][0].source == "pmc"


def test_openalex_repository_candidates_ignore_publisher_pdf_urls() -> None:
    doi = "10.1000/example"
    url = "https://api.openalex.org/works/doi:10.1000%2Fexample"
    client = FakeClient(
        json_by_url={
            url: {
                "open_access": {"oa_url": "https://www.nature.com/articles/example.pdf"},
                "best_oa_location": {
                    "pdf_url": "https://www.nature.com/articles/example.pdf",
                    "source": {"type": "journal", "display_name": "Publisher Journal"},
                },
                "locations": [
                    {
                        "pdf_url": "https://repo.example/files/article.pdf",
                        "landing_page_url": "https://repo.example/item/1",
                        "source": {"type": "repository", "display_name": "Institutional Repository"},
                        "version": "acceptedVersion",
                    }
                ],
            }
        }
    )

    candidates, events = openalex_repository_candidates(client, doi)

    assert [candidate.url for candidate in candidates] == [
        "https://repo.example/files/article.pdf",
        "https://repo.example/item/1",
    ]
    assert events[0]["pdf_candidate_count"] == 2


def test_semantic_scholar_candidates_return_open_access_pdf_url() -> None:
    doi = "10.1000/example"
    url = "https://api.semanticscholar.org/graph/v1/paper/DOI%3A10.1000%2Fexample?fields=title,year,isOpenAccess,openAccessPdf,externalIds,url"
    client = FakeClient(
        json_by_url={
            url: {
                "title": "Example",
                "openAccessPdf": {"url": "https://repo.example/example.pdf", "status": "GREEN"},
            }
        }
    )

    candidates, events = semantic_scholar_candidates(client, doi)

    assert [candidate.url for candidate in candidates] == ["https://repo.example/example.pdf"]
    assert candidates[0].source == "semantic_scholar"
    assert events[0]["pdf_candidate_count"] == 1
