from pipeline.fulltext.recover_pdf_landing_pages import (
    figshare_article_ids,
    figshare_download_urls_for_article,
    has_standard_recovery_signal,
    is_challenge_page,
    osf_guid_candidates,
    rescue_preset_categories,
    rescue_preset_hosts,
    same_host_pdf_links,
    selected_rows,
    try_candidate,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        url: str = "https://example.test/",
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        json_payload: dict | None = None,
    ):
        self.status_code = status_code
        self.url = url
        self.content = content
        self.headers = headers or {}
        self._json_payload = json_payload

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> dict:
        if self._json_payload is None:
            raise ValueError("No JSON payload")
        return self._json_payload


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs) -> FakeResponse:
        self.calls.append(url)
        response = self.responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL: {url}")
        return response


def test_challenge_pages_are_detected() -> None:
    assert is_challenge_page("<html><title>Preparing</title><script src='recaptcha.js'></script></html>")
    assert is_challenge_page("<h2>Gauging your humanity...This may take some seconds.</h2>")
    assert is_challenge_page("<script>AwsWafIntegration.checkForceRefresh()</script>")


def test_same_host_pdf_links_are_extracted_from_repository_landing_page() -> None:
    html = """
    <a href="/files/paper.pdf">Download file</a>
    <a href="https://other.example/paper.pdf">External PDF</a>
    """

    links = same_host_pdf_links("https://repo.example/item/123", html)

    assert links == ["https://repo.example/files/paper.pdf"]


def test_springer_pages_do_not_extract_reference_pdf_links() -> None:
    html = """
    <a href="https://static-content.springer.com/esm/art%3A10.1007%2Fexample/MediaObjects/file.pdf">Supplement</a>
    <a href="http://www.fda.gov/downloads/Drugs/example.pdf">Reference PDF</a>
    """

    links = same_host_pdf_links("https://link.springer.com/article/10.1007/example", html)

    assert links == []


def test_osf_guid_candidates_extract_doi_and_preprint_urls() -> None:
    assert osf_guid_candidates("10.31234/osf.io/3ykst") == ["3ykst"]
    assert osf_guid_candidates("https://osf.io/preprints/psyarxiv/p5m2f_v2/download") == [
        "p5m2f_v2",
        "p5m2f",
    ]


def test_figshare_article_ids_extract_repository_article_id() -> None:
    assert figshare_article_ids(
        "https://openaccess.wgtn.ac.nz/articles/thesis/Example_Title/30193615/1/files/58179229.pdf"
    ) == ["30193615"]


def test_figshare_api_accepts_pdf_mimetype_without_pdf_url_suffix() -> None:
    session = FakeSession(
        {
            "https://api.figshare.com/v2/articles/23490149": FakeResponse(
                url="https://api.figshare.com/v2/articles/23490149",
                headers={"content-type": "application/json"},
                content=b"{}",
                json_payload={
                    "files": [
                        {
                            "name": "Jelen_Ketamine_for_Depression_accepted_2020.pdf",
                            "download_url": "https://ndownloader.figshare.com/files/41198684",
                            "mimetype": "application/pdf",
                        }
                    ]
                },
            )
        }
    )

    urls, events = figshare_download_urls_for_article(session, "23490149", timeout_sec=10)

    assert urls == ["https://ndownloader.figshare.com/files/41198684"]
    assert events[-1]["mimetype"] == "application/pdf"


def test_standard_recovery_signal_accepts_osf_and_figshare_rows() -> None:
    assert has_standard_recovery_signal({"doi": "10.31234/osf.io/3ykst"})
    assert has_standard_recovery_signal(
        {
            "pdf_url_candidates": (
                "https://openaccess.wgtn.ac.nz/articles/thesis/"
                "Example_Title/30193615/1/files/58179229.pdf"
            )
        }
    )
    assert has_standard_recovery_signal(
        {
            "best_pdf_url": (
                "http://sro.sussex.ac.uk/id/eprint/106470/1/"
                "Jelen_Ketamine_for_Depression_accepted_2020.pdf"
            )
        }
    )
    assert not has_standard_recovery_signal({"best_pdf_url": "https://publisher.example/article.pdf"})


def test_try_candidate_follows_figshare_redirect_to_api_download() -> None:
    source_url = "http://sro.sussex.ac.uk/id/eprint/106470/1/example.pdf"
    api_url = "https://api.figshare.com/v2/articles/23490149"
    download_url = "https://ndownloader.figshare.com/files/41198684"
    pdf_body = b"%PDF-1.6\nbody"
    session = FakeSession(
        {
            source_url: FakeResponse(
                url="https://sussex.figshare.com/articles/journal_contribution/Ketamine_for_depression/23490149",
                status_code=202,
                headers={"content-type": "text/html"},
                content=b"<html><script>AwsWafIntegration.checkForceRefresh()</script></html>",
            ),
            api_url: FakeResponse(
                url=api_url,
                headers={"content-type": "application/json"},
                json_payload={
                    "files": [
                        {
                            "name": "accepted.pdf",
                            "download_url": download_url,
                            "mimetype": "application/pdf",
                        }
                    ]
                },
            ),
            download_url: FakeResponse(
                url="https://s3.example/accepted.pdf",
                headers={"content-type": "application/pdf"},
                content=pdf_body,
            ),
        }
    )

    selected_url, body, events = try_candidate(
        session=session,
        url=source_url,
        timeout_sec=10,
        allow_landing_resolution=True,
    )

    assert selected_url == "https://s3.example/accepted.pdf"
    assert body == pdf_body
    assert [event["event"] for event in events] == [
        "candidate_response",
        "figshare_article_response",
        "figshare_file",
        "figshare_download_response",
    ]


def test_selected_rows_standard_recovery_only_filters_broad_publisher_failures() -> None:
    import pandas as pd

    rows = pd.DataFrame(
        [
            {
                "doi": "10.31234/osf.io/3ykst",
                "pdf_download_failure_category": "non_pdf_response",
                "best_pdf_url": "https://osf.io/3ykst/download",
            },
            {
                "doi": "10.1000/publisher",
                "pdf_download_failure_category": "forbidden",
                "best_pdf_url": "https://publisher.example/article.pdf",
            },
        ]
    )

    selected = selected_rows(
        rows,
        doi_filter=None,
        hosts=set(),
        categories={"forbidden", "non_pdf_response"},
        standard_recovery_only=True,
    )

    assert [row["doi"] for row in selected] == ["10.31234/osf.io/3ykst"]


def test_akjournals_rescue_preset_selects_host_and_broad_categories() -> None:
    import pandas as pd

    rows = pd.DataFrame(
        [
            {
                "doi": "10.1556/example",
                "pdf_download_failure_category": "forbidden",
                "best_pdf_url": "https://akjournals.com/view/journals/2054/example",
            },
            {
                "doi": "10.1007/example",
                "pdf_download_failure_category": "forbidden",
                "best_pdf_url": "https://link.springer.com/content/pdf/example.pdf",
            },
        ]
    )

    selected = selected_rows(
        rows,
        doi_filter=None,
        hosts=rescue_preset_hosts("akjournals"),
        categories=rescue_preset_categories("akjournals"),
        standard_recovery_only=False,
    )

    assert [row["doi"] for row in selected] == ["10.1556/example"]
