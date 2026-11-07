import json
from collections import Counter
from pathlib import Path

from pipeline.fulltext.source_identity import (
    DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
    apply_pdf_hash_attestation,
    evaluate_artifact_identity,
    jats_article_identities,
    load_pdf_hash_attestation_registry,
    normalize_doi,
    select_jats_article,
    split_dois,
    tei_header_identity,
)


def extraction(backend: str, text: str, format_name: str) -> dict:
    return {
        "backend": backend,
        "status": "ok",
        "char_count": len(text),
        "section_count": 1,
        "sections": [],
        "text": text,
        "metadata": {"format": format_name},
    }


def test_jats_identity_uses_article_meta_not_cited_references() -> None:
    xml = """
    <article>
      <front><article-meta>
        <article-id pub-id-type="doi">10.1000/requested</article-id>
        <article-id pub-id-type="pmcid">PMC123</article-id>
        <title-group><article-title>Requested paper</article-title></title-group>
      </article-meta></front>
      <back><ref-list><ref><element-citation>
        <pub-id pub-id-type="doi">10.1000/cited</pub-id>
      </element-citation></ref></ref-list></back>
    </article>
    """

    identities = jats_article_identities(xml)

    assert len(identities) == 1
    assert identities[0]["doi"] == "10.1000/requested"
    assert identities[0]["pmcid"] == "PMC123"


def test_select_jats_article_slices_matching_subarticle() -> None:
    xml = """
    <article>
      <front><article-meta>
        <article-id pub-id-type="doi">10.1000/container</article-id>
        <title-group><article-title>Container</article-title></title-group>
      </article-meta></front>
      <sub-article><front-stub>
        <article-id pub-id-type="doi">10.1000/target</article-id>
        <title-group><article-title>Target abstract</article-title></title-group>
      </front-stub><body><p>Target result.</p></body></sub-article>
    </article>
    """

    selected, identity = select_jats_article(xml, "10.1000/target")

    assert identity["doi"] == "10.1000/target"
    assert "Target result" in selected
    assert "<sub-article" in selected


def test_tei_identity_is_limited_to_header_source_description() -> None:
    tei = """
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <teiHeader><fileDesc>
        <titleStmt><title>Requested paper</title></titleStmt>
        <sourceDesc><biblStruct><analytic>
          <idno type="DOI">10.1000/requested</idno>
        </analytic></biblStruct></sourceDesc>
      </fileDesc></teiHeader>
      <text><back><listBibl><biblStruct><analytic>
        <idno type="DOI">10.1000/cited</idno>
      </analytic></biblStruct></listBibl></back></text>
    </TEI>
    """

    identity = tei_header_identity(tei)

    assert identity["doi"] == "10.1000/requested"
    assert identity["title"] == "Requested paper"


def test_artifact_identity_rejects_wrong_xml_even_when_wrapper_doi_matches() -> None:
    xml = """
    <article><front><article-meta>
      <article-id pub-id-type="doi">10.1000/other</article-id>
      <title-group><article-title>Unrelated source</article-title></title-group>
    </article-meta></front><body><p>Other content.</p></body></article>
    """
    artifact = {
        "study_doi": "10.1000/requested",
        "study_title": "Requested paper",
        "best_backend": "pmc_oai_xml",
        "extractions": [extraction("pmc_oai_xml", xml, "jats_xml")],
    }

    identity = evaluate_artifact_identity(artifact)

    assert identity["status"] == "identity_mismatch"
    assert not identity["verified"]


def test_artifact_identity_accepts_explicit_version_doi_with_matching_title() -> None:
    tei = """
    <TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>
      <titleStmt><title>Same scientific paper</title></titleStmt>
      <sourceDesc><biblStruct><analytic><idno type="DOI">10.1000/preprint</idno></analytic></biblStruct></sourceDesc>
    </fileDesc></teiHeader><text><body><p>Result.</p></body></text></TEI>
    """
    artifact = {
        "study_doi": "10.1000/published",
        "study_title": "Same scientific paper",
        "best_backend": "grobid",
        "extractions": [extraction("grobid", tei, "tei_xml")],
    }

    identity = evaluate_artifact_identity(artifact, related_dois=["10.1000/preprint"])

    assert identity["status"] == "verified_related_doi"
    assert identity["verified"]


def test_title_only_identity_does_not_accept_title_later_in_container() -> None:
    target = "Trace amine receptor as a target for cognitive dysfunction"
    tei = f"""
    <TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>
      <titleStmt><title>Adjacent conference abstract</title></titleStmt>
      <sourceDesc><biblStruct><analytic /></biblStruct></sourceDesc>
    </fileDesc></teiHeader><text><body>
      <p>{'unrelated material ' * 900}</p>
      <div><head>{target}</head><p>Target abstract text.</p></div>
    </body></text></TEI>
    """
    artifact = {
        "study_doi": "10.1000/target",
        "study_title": target,
        "best_backend": "grobid",
        "extractions": [extraction("grobid", tei, "tei_xml")],
    }

    identity = evaluate_artifact_identity(artifact)

    assert identity["title_phrase_match"] is True
    assert identity["front_title_phrase_match"] is False
    assert identity["status"] == "identity_unverified"
    assert identity["verified"] is False


def test_legacy_sici_doi_is_not_truncated_at_angle_brackets() -> None:
    doi = "10.1002/(SICI)1521-3838(199912)18:6<548::AID-QSAR548>3.0.CO;2-B"

    assert normalize_doi(doi) == doi.lower()
    assert split_dois(f"DOI: {doi}") == {doi.lower()}


def test_pdf_hash_attestation_registry_is_curated_and_hash_bound() -> None:
    registry = load_pdf_hash_attestation_registry(DEFAULT_PDF_HASH_ATTESTATION_REGISTRY)

    # The registry is intentionally appendable as new exact-byte curator
    # attestations are added. The loader already validates record_count and
    # uniqueness, so this test should not fail merely because the curated set
    # grew.
    assert len(registry["records"]) >= 30
    record = registry["records"]["10.1254/fpj.97.4/209"]
    assert record["document_kind"] == "single_article_pdf"
    assert len(record["pdf_sha256"]) == 64
    assert all(row["document_kind"] == "single_article_pdf" for row in registry["records"].values())
    assert all(len(row["pdf_sha256"]) == 64 for row in registry["records"].values())
    assert "10.17992/lbl.2023.11.766" in registry["records"]
    assert "10.1002/hup.1270" in registry["records"]


def test_doi_normalization_removes_concatenated_pubmed_identifier() -> None:
    assert normalize_doi("10.1371/journal.pone.0059334pmid:23527166") == "10.1371/journal.pone.0059334"


def test_curated_pdf_hash_attestation_rechecks_exact_file(tmp_path: Path) -> None:
    import hashlib

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-reviewed-single-article")
    sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    artifact = {
        "study_doi": "10.1000/multilingual",
        "pdf_local_path": str(pdf),
        "pdf_sha256": sha256,
    }
    record = {
        "requested_doi": "10.1000/multilingual",
        "pdf_sha256": sha256,
        "review_basis": "Original-language title was manually checked.",
        "reviewed_at": "2026-07-10",
        "source_url": "https://publisher.example/article.pdf",
    }
    identity = {"status": "identity_unverified", "verified": False}

    accepted = apply_pdf_hash_attestation(identity, artifact, record)
    assert accepted["status"] == "verified_curated_pdf_hash"
    assert accepted["pdf_hash_attestation_applied"] is True

    pdf.write_bytes(b"%PDF-different-file")
    rejected = apply_pdf_hash_attestation(identity, artifact, record)
    assert rejected["verified"] is False
    assert rejected["pdf_hash_attestation_disposition"] == "pdf_hash_mismatch"


def test_pdf_cover_title_cannot_override_conflicting_article_doi(tmp_path, monkeypatch) -> None:
    from pipeline.fulltext.source_identity import apply_pdf_front_title_validation
    from pipeline.fulltext import pdf_alternate_sources

    pdf = tmp_path / "repository-cover-with-wrong-article.pdf"
    pdf.write_bytes(b"%PDF-cover")
    monkeypatch.setattr(pdf_alternate_sources, "title_validation_result",
                        lambda *args: (_ for _ in ()).throw(AssertionError("must not use cover")))
    for status in ("target_text_with_conflicting_doi", "identity_mismatch"):
        result = apply_pdf_front_title_validation(
            {"status": status, "verified": False, "document_doi": "10.1000/wrong"},
            {"pdf_local_path": str(pdf)}, requested_title="Requested title on cover")
        assert not result["verified"]
        assert result["status"] == status
        assert result["pdf_front_title_validation_disposition"] == "document_doi_conflict_requires_resolution"


