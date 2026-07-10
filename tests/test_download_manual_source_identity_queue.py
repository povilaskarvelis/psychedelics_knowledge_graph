import csv
import hashlib
import json
from pathlib import Path

from pipeline.fulltext import download_manual_source_identity_queue as downloader
from pipeline.ingest.sync_paper_library import pdf_filename_for_doi


def write_queue(path: Path, rows: list[dict]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def queue_row(doi: str, title: str, **updates) -> dict:
    row = {
        "doi": doi,
        "title": title,
        "priority_eligible": "True",
        "priority_tier": "P1_existing_kg_or_curated_signal",
        "priority_score": "80",
        "kg_finding_count": "0",
        "final_action_category": "manual_identity_unverified",
        "verified_pmcid": "",
        "curated_exact_pdf_urls": "",
        "candidate_urls_requiring_validation": "",
        "candidate_url_evidence_json": "[]",
    }
    row.update(updates)
    return row


def test_queue_candidates_are_rescreened_and_include_verified_resolvers() -> None:
    row = queue_row(
        "10.1000/example",
        "A sufficiently specific requested article title",
        verified_pmcid="PMC123",
        curated_exact_pdf_urls="https://repo.example/article.pdf",
        candidate_urls_requiring_validation=(
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/main.pdf | "
            "https://publisher.example/doi/pdf/10.1000/example | "
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC999/pdf/wrong.pdf | "
            "https://repo.example/supplement.pdf | "
            "http://dx.doi.org/10.1000/example"
        ),
        candidate_url_evidence_json=json.dumps(
            [
                {
                    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/main.pdf",
                    "source": "metadata.pdf_url_candidates",
                }
            ]
        ),
    )

    candidates, exclusions = downloader.candidate_records_from_queue_row(row)

    assert [candidate.url for candidate in candidates] == [
        "https://repo.example/article.pdf",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/main.pdf",
        "https://publisher.example/doi/pdf/10.1000/example",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
        "https://doi.org/10.1000/example",
    ]
    assert candidates[1].source == "queue_candidate:metadata.pdf_url_candidates"
    assert {item["reason"] for item in exclusions} == {
        "unverified_or_stale_pmcid",
        "ancillary_url_pattern",
    }


def test_manual_url_registry_is_attempted_before_stale_queue_candidates(tmp_path: Path) -> None:
    registry = tmp_path / "manual_urls.json"
    registry.write_text(
        json.dumps(
            [
                {
                    "doi": "10.1000/example",
                    "urls": ["https://publisher.example/exact.pdf"],
                }
            ]
        ),
        encoding="utf-8",
    )
    loaded = downloader.load_manual_urls(registry)
    candidates, _ = downloader.candidate_records_from_queue_row(
        queue_row(
            "10.1000/example",
            "Requested article title with enough specific words",
            candidate_urls_requiring_validation="https://repo.example/stale.pdf",
        ),
        manual_urls=loaded["10.1000/example"],
    )

    assert [candidate.url for candidate in candidates[:2]] == [
        "https://publisher.example/exact.pdf",
        "https://repo.example/stale.pdf",
    ]
    assert candidates[0].source == "manual_url_registry"


def test_select_queue_rows_applies_priority_filters_before_limit() -> None:
    rows = [
        queue_row("10.1000/low", "Low title", priority_tier="P2_retained_candidate", priority_score="100"),
        queue_row("10.1000/high", "High title", priority_tier="P0_existing_kg_and_retained", priority_score="1200"),
        queue_row(
            "10.1000/not-priority",
            "Not priority",
            priority_eligible="False",
            priority_tier="not_in_priority_queue",
            priority_score="0",
        ),
    ]

    selected = downloader.select_queue_rows(
        rows,
        priority_only=True,
        priority_tiers={"P0_existing_kg_and_retained", "P2_retained_candidate"},
        min_priority_score=50,
        limit=1,
    )

    assert [row["doi"] for row in selected] == ["10.1000/high"]

    assert downloader.select_queue_rows(rows, doi_filter=set()) == []


def test_select_queue_rows_never_selects_abstract_only_or_no_public_fulltext() -> None:
    rows = [
        queue_row(
            "10.1000/abstract-only",
            "Public abstract only",
            repair_eligible="False",
            recommended_acquisition_route="none_active_route_does_not_require_full_text",
        ),
        queue_row(
            "10.1000/no-public-fulltext",
            "No publicly available full text",
            repair_eligible="True",
            curated_access_status="user_confirmed_no_public_full_text",
        ),
        queue_row(
            "10.1000/public-repair",
            "Public source repair",
            repair_eligible="True",
            recommended_acquisition_route="public_source_discovery",
        ),
    ]

    selected = downloader.select_queue_rows(rows)

    assert [row["doi"] for row in selected] == ["10.1000/public-repair"]


def test_validate_downloaded_pdf_accepts_exact_front_doi(monkeypatch) -> None:
    monkeypatch.setattr(
        downloader,
        "extract_pdf_identity_texts",
        lambda _body: ("DOI: 10.1000/example\nUnrelated visible title", ""),
    )

    result = downloader.validate_downloaded_pdf(
        doi="10.1000/example",
        title="Requested article title with enough specific words",
        body=b"%PDF-1.7\nbody",
        pdf_hash_attestations={},
    )

    assert result["accepted"] is True
    assert result["basis"] == "document_front_doi"


def test_validate_downloaded_pdf_accepts_only_bounded_page_top_title(monkeypatch) -> None:
    requested = "Requested article title with enough specific words"
    monkeypatch.setattr(
        downloader,
        "extract_pdf_identity_texts",
        lambda _body: (f"{requested}\n" + "substantive text " * 40, ""),
    )
    accepted = downloader.validate_downloaded_pdf(
        doi="10.1000/example",
        title=requested,
        body=b"%PDF-1.7\nfront",
        pdf_hash_attestations={},
    )

    monkeypatch.setattr(
        downloader,
        "extract_pdf_identity_texts",
        lambda _body: ("Different article on page one\n" + "body " * 80 + f"\f{requested}", ""),
    )
    rejected = downloader.validate_downloaded_pdf(
        doi="10.1000/example",
        title=requested,
        body=b"%PDF-1.7\nlater",
        pdf_hash_attestations={},
    )

    assert accepted["accepted"] is True
    assert accepted["basis"] == "bounded_page_top_title"
    assert rejected["accepted"] is False
    assert rejected["basis"] == "front_title_mismatch"


def test_validate_downloaded_pdf_rejects_conflicting_front_doi_before_title(monkeypatch) -> None:
    requested = "Requested article title with enough specific words"
    monkeypatch.setattr(
        downloader,
        "extract_pdf_identity_texts",
        lambda _body: (f"DOI: 10.1000/wrong\n{requested}\n" + "body " * 80, ""),
    )

    result = downloader.validate_downloaded_pdf(
        doi="10.1000/example",
        title=requested,
        body=b"%PDF-1.7\nbody",
        pdf_hash_attestations={},
    )

    assert result["accepted"] is False
    assert result["basis"] == "document_front_doi_conflict"


def test_validate_downloaded_pdf_accepts_exact_curated_hash(monkeypatch) -> None:
    body = b"%PDF-1.7\nreviewed bytes"
    monkeypatch.setattr(
        downloader,
        "extract_pdf_identity_texts",
        lambda _body: (_ for _ in ()).throw(AssertionError("hash match should short-circuit extraction")),
    )

    result = downloader.validate_downloaded_pdf(
        doi="10.1000/example",
        title="",
        body=body,
        pdf_hash_attestations={
            "10.1000/example": {"pdf_sha256": hashlib.sha256(body).hexdigest()}
        },
    )

    assert result["accepted"] is True
    assert result["basis"] == "curated_pdf_hash"


class FakeClient:
    def __init__(self, responses: dict[str, bytes]):
        self.responses = responses
        self.calls: list[str] = []

    def get_bytes(self, url: str, headers=None) -> bytes:
        self.calls.append(url)
        return self.responses[url]


def test_dry_run_writes_plan_without_network_or_inbox(tmp_path: Path) -> None:
    queue = tmp_path / "queue.csv"
    report_path = tmp_path / "report.json"
    inbox = tmp_path / "inbox"
    write_queue(
        queue,
        [
            queue_row(
                "10.1000/example",
                "Requested article title with enough specific words",
                candidate_urls_requiring_validation="https://repo.example/article.pdf",
            )
        ],
    )
    client = FakeClient({})

    report = downloader.download_manual_queue(
        queue_csv=queue,
        inbox_dir=inbox,
        report_path=report_path,
        apply=False,
        client=client,
        pdf_hash_attestations={},
    )

    assert report["counts"] == {"planned": 1}
    assert client.calls == []
    assert not inbox.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["apply"] is False


def test_apply_tries_next_candidate_and_atomically_saves_only_validated_pdf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    doi = "10.1000/example"
    queue = tmp_path / "queue.csv"
    report_path = tmp_path / "report.json"
    inbox = tmp_path / "inbox"
    first_url = "https://repo.example/wrong.pdf"
    second_url = "https://repo.example/right.pdf"
    wrong = b"%PDF-1.7\nwrong"
    right = b"%PDF-1.7\nright"
    write_queue(
        queue,
        [
            queue_row(
                doi,
                "Requested article title with enough specific words",
                candidate_urls_requiring_validation=f"{first_url} | {second_url}",
            )
        ],
    )
    client = FakeClient({first_url: wrong, second_url: right})

    def fake_validation(*, body: bytes, **_kwargs) -> dict:
        return {
            "accepted": body == right,
            "basis": "bounded_page_top_title" if body == right else "front_title_mismatch",
            "pdf_sha256": hashlib.sha256(body).hexdigest(),
            "pdf_size": len(body),
        }

    monkeypatch.setattr(downloader, "validate_downloaded_pdf", fake_validation)

    report = downloader.download_manual_queue(
        queue_csv=queue,
        inbox_dir=inbox,
        report_path=report_path,
        apply=True,
        client=client,
        pdf_hash_attestations={},
    )

    destination = inbox / pdf_filename_for_doi(doi)
    assert destination.read_bytes() == right
    assert report["counts"] == {"downloaded_validated": 1}
    assert [attempt["status"] for attempt in report["records"][0]["attempts"]] == [
        "identity_rejected",
        "accepted_saved",
    ]
    assert client.calls == [first_url, second_url]
    assert list(inbox.glob(".*.tmp")) == []


def test_apply_never_saves_identity_rejected_pdf(tmp_path: Path, monkeypatch) -> None:
    doi = "10.1000/example"
    queue = tmp_path / "queue.csv"
    report_path = tmp_path / "report.json"
    inbox = tmp_path / "inbox"
    url = "https://repo.example/wrong.pdf"
    write_queue(
        queue,
        [
            queue_row(
                doi,
                "Requested article title with enough specific words",
                candidate_urls_requiring_validation=url,
            )
        ],
    )
    client = FakeClient({url: b"%PDF-1.7\nwrong", downloader.doi_landing_url(doi): b"<html>closed</html>"})
    monkeypatch.setattr(
        downloader,
        "validate_downloaded_pdf",
        lambda **_kwargs: {
            "accepted": False,
            "basis": "front_title_mismatch",
            "pdf_sha256": "0" * 64,
            "pdf_size": 16,
        },
    )

    report = downloader.download_manual_queue(
        queue_csv=queue,
        inbox_dir=inbox,
        report_path=report_path,
        apply=True,
        client=client,
        pdf_hash_attestations={},
    )

    assert report["counts"] == {"download_failed": 1}
    assert not (inbox / pdf_filename_for_doi(doi)).exists()
