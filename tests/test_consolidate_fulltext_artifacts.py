import json
from pathlib import Path
import tempfile

from pipeline.fulltext.consolidate_fulltext_artifacts import consolidate_fulltext_artifacts
from pipeline.fulltext.convert_pdfs import doi_to_slug


def write_artifact(
    path: Path,
    doi: str,
    dataset: str,
    chars: int,
    backend: str = "grobid",
    identity_status: str | None = "verified_exact_doi",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dataset": dataset,
                "study_doi": doi,
                "best_backend": backend,
                "best_char_count": chars,
                "best_section_count": 1,
                "extractions": [],
                **(
                    {"source_identity": {"status": identity_status}}
                    if identity_status is not None
                    else {}
                ),
            }
        ),
        encoding="utf-8",
    )


def test_consolidates_best_artifact_per_doi_into_articles_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fulltext_dir = Path(tmp) / "fulltext"
        doi = "10.1000/example"
        slug = doi_to_slug(doi)
        write_artifact(fulltext_dir / "mechanistic" / f"{slug}.json", doi, "mechanistic", 500)
        write_artifact(fulltext_dir / "disorder" / f"{slug}.json", doi, "disorder", 1000)
        target_dir = fulltext_dir / "articles"
        report = consolidate_fulltext_artifacts(
            fulltext_dir=fulltext_dir,
            target_dir=target_dir,
            report_path=fulltext_dir / "report.json",
        )
        artifact = json.loads((target_dir / f"{slug}.json").read_text(encoding="utf-8"))

    assert report["counts"]["unique_dois"] == 1
    assert report["counts"]["doi_with_duplicate_sources"] == 1
    assert artifact["dataset"] == "articles"
    assert artifact["source_artifact_dataset"] == "disorder"
    assert artifact["best_char_count"] == 1000
    assert artifact["fulltext_artifact_layout"] == "canonical_articles_v1"


def test_consolidation_preserves_existing_target_without_overwrite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fulltext_dir = Path(tmp) / "fulltext"
        doi = "10.1000/example"
        slug = doi_to_slug(doi)
        write_artifact(fulltext_dir / "mechanistic" / f"{slug}.json", doi, "mechanistic", 500)
        write_artifact(fulltext_dir / "articles" / f"{slug}.json", doi, "articles", 2000)

        report = consolidate_fulltext_artifacts(
            fulltext_dir=fulltext_dir,
            target_dir=fulltext_dir / "articles",
            report_path=fulltext_dir / "report.json",
            overwrite=False,
        )
        artifact = json.loads((fulltext_dir / "articles" / f"{slug}.json").read_text(encoding="utf-8"))

    assert report["counts"]["skipped_existing"] == 1
    assert artifact["best_char_count"] == 2000


def test_consolidation_does_not_write_explicit_identity_mismatch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fulltext_dir = Path(tmp) / "fulltext"
        doi = "10.1000/wrong"
        slug = doi_to_slug(doi)
        source = fulltext_dir / "mechanistic" / f"{slug}.json"
        write_artifact(source, doi, "mechanistic", 500)
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["source_identity"] = {"status": "identity_mismatch"}
        source.write_text(json.dumps(payload), encoding="utf-8")

        report = consolidate_fulltext_artifacts(
            fulltext_dir=fulltext_dir,
            target_dir=fulltext_dir / "articles",
            report_path=fulltext_dir / "report.json",
        )

    assert report["counts"]["skipped_identity_unverified"] == 1
    assert not (fulltext_dir / "articles" / f"{slug}.json").exists()


def test_consolidation_does_not_write_missing_identity_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fulltext_dir = Path(tmp) / "fulltext"
        doi = "10.1000/legacy"
        slug = doi_to_slug(doi)
        write_artifact(
            fulltext_dir / "mechanistic" / f"{slug}.json",
            doi,
            "mechanistic",
            500,
            identity_status=None,
        )

        report = consolidate_fulltext_artifacts(
            fulltext_dir=fulltext_dir,
            target_dir=fulltext_dir / "articles",
            report_path=fulltext_dir / "report.json",
        )

    assert report["counts"]["skipped_identity_unverified"] == 1


def test_consolidation_refuses_slug_collision_between_dois() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fulltext_dir = Path(tmp) / "fulltext"
        first = "10.1000/a:b"
        second = "10.1000/a/b"
        slug = doi_to_slug(first)
        assert slug == doi_to_slug(second)
        write_artifact(fulltext_dir / "articles" / f"{slug}.json", first, "articles", 1000)
        write_artifact(fulltext_dir / "mechanistic" / f"{slug}.json", second, "mechanistic", 2000)

        report = consolidate_fulltext_artifacts(
            fulltext_dir=fulltext_dir,
            target_dir=fulltext_dir / "articles",
            report_path=fulltext_dir / "report.json",
            overwrite=True,
        )
        artifact = json.loads((fulltext_dir / "articles" / f"{slug}.json").read_text())

    assert report["counts"]["skipped_target_doi_collision"] == 1
    assert artifact["study_doi"] == first
