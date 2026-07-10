import json
from collections import Counter
from pathlib import Path

from pipeline.fulltext.audit_fulltext_source_identity import (
    DEFAULT_IDENTITY_REGISTRY,
    apply_validated_pdf_repair_attestation,
    apply_identity_registry,
    audit_artifacts,
    load_identity_registry,
    reject_correction_artifact_for_main_record,
)

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


def test_persistent_identity_registry_has_all_curated_benign_classes() -> None:
    registry = load_identity_registry(DEFAULT_IDENTITY_REGISTRY)

    assert len(registry["records"]) == 109
    assert registry["minimum_front_title_similarity"] == 0.9
    assert Counter(row["relationship_type"] for row in registry["records"].values()) == {
        "preprint_repository_version": 33,
        "doi_parse_truncation_or_suffix": 43,
        "grobid_related_doi_misidentification": 16,
        "publisher_language_alias": 2,
        "publisher_doi_alias": 2,
        "correction_record_to_original_doi": 12,
        "article_version": 1,
    }
    assert Counter(row["identity_action"] for row in registry["records"].values()) == {
        "accept_related_document_doi": 37,
        "accept_correction_original_doi": 12,
        "ignore_incorrect_extracted_document_doi": 58,
        "no_override_required": 2,
    }
    assert Counter(row["record_group"] for row in registry["records"].values()) == {
        "benign_conflict": 73,
        "correction_record": 12,
        "pmc_valid_exact": 23,
        "pmc_valid_known_alias": 1,
    }


def test_pdf_hash_attestation_registry_is_narrow_and_hash_bound() -> None:
    registry = load_pdf_hash_attestation_registry(DEFAULT_PDF_HASH_ATTESTATION_REGISTRY)

    assert len(registry["records"]) == 8
    record = registry["records"]["10.1254/fpj.97.4_209"]
    assert record["document_kind"] == "single_article_pdf"
    assert len(record["pdf_sha256"]) == 64
    assert all(row["document_kind"] == "single_article_pdf" for row in registry["records"].values())
    assert all(len(row["pdf_sha256"]) == 64 for row in registry["records"].values())
    assert "10.17992/lbl.2023.11.766" in registry["records"]


def test_doi_normalization_removes_concatenated_pubmed_identifier() -> None:
    assert normalize_doi("10.1371/journal.pone.0059334pmid:23527166") == "10.1371/journal.pone.0059334"


def test_registry_relation_requires_matching_doi_and_front_title_evidence() -> None:
    identity = {
        "status": "identity_mismatch",
        "verified": False,
        "evidence": [
            {
                "document_doi": "10.1000/preprint",
                "document_title": "Unrelated journal banner",
                "title_similarity": 0.2,
                "title_coverage": 1.0,
                "title_phrase_match": True,
                "front_title_phrase_match": False,
                "backend": "grobid",
                "format": "tei_xml",
            }
        ],
    }
    record = {
        "requested_doi": "10.1000/published",
        "observed_document_doi": "10.1000/preprint",
        "relationship_type": "preprint_repository_version",
        "identity_action": "accept_related_document_doi",
    }

    result = apply_identity_registry(identity, record, minimum_title_similarity=0.85)

    assert not result["verified"]
    assert not result["registry_applied"]
    assert result["registry_disposition"] == "unresolved_insufficient_front_title_evidence"


def test_registry_identifier_override_accepts_strong_front_title() -> None:
    identity = {
        "status": "target_text_with_conflicting_doi",
        "verified": False,
        "evidence": [
            {
                "document_doi": "10.1000/truncated",
                "document_title": "The requested scientific paper",
                "title_similarity": 0.96,
                "title_coverage": 1.0,
                "title_phrase_match": True,
                "front_title_phrase_match": True,
                "backend": "grobid",
                "format": "tei_xml",
            }
        ],
    }
    record = {
        "requested_doi": "10.1000/truncated.123",
        "observed_document_doi": "10.1000/truncated",
        "relationship_type": "doi_parse_truncation_or_suffix",
        "identity_action": "ignore_incorrect_extracted_document_doi",
    }

    result = apply_identity_registry(identity, record, minimum_title_similarity=0.85)

    assert result["verified"]
    assert result["status"] == "verified_identity_override"
    assert result["registry_applied"]
    assert result["registry_disposition"] == "applied_front_title_corroborated"


def test_registry_never_overrides_a_new_exact_artifact() -> None:
    identity = {
        "status": "verified_exact_doi",
        "verified": True,
        "document_doi": "10.1000/published",
        "evidence": [],
    }
    old_relation = {
        "requested_doi": "10.1000/published",
        "observed_document_doi": "10.1000/preprint",
        "relationship_type": "preprint_repository_version",
        "identity_action": "accept_related_document_doi",
    }

    result = apply_identity_registry(identity, old_relation, minimum_title_similarity=0.85)

    assert result["status"] == "verified_exact_doi"
    assert result["document_doi"] == "10.1000/published"
    assert not result["registry_applied"]
    assert result["registry_disposition"] == "not_needed_exact_identity"


def test_validated_pdf_repair_attestation_rechecks_hash(tmp_path: Path) -> None:
    import hashlib

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-validated-content")
    artifact = {
        "study_doi": "10.1000/published",
        "repair_run_id": "source_identity_repair_20260710",
        "fulltext_source": "validated_pdf_source_identity_repair",
        "pdf_local_path": str(pdf),
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "source_identity": {
            "status": "verified_title_only",
            "verified": True,
            "requested_doi": "10.1000/published",
            "pdf_front_page_validation": {
                "accepted": True,
                "reason": "verified_front_page",
                "title_score": 0.95,
                "front_page_char_count": 500,
            },
        },
    }
    identity = {"status": "identity_unverified", "verified": False}

    accepted = apply_validated_pdf_repair_attestation(identity, artifact)
    assert accepted["verified"] is True
    assert accepted["repair_attestation_applied"] is True

    pdf.write_bytes(b"%PDF-tampered")
    rejected = apply_validated_pdf_repair_attestation(identity, artifact)
    assert rejected["verified"] is False
    assert rejected["repair_attestation_applied"] is False


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


def test_correction_relationship_requires_requested_correction_title() -> None:
    identity = {
        "status": "target_text_with_conflicting_doi",
        "verified": False,
        "requested_title": "Main scientific article",
        "evidence": [
            {
                "document_doi": "10.1000/correction",
                "document_title": "Correction: Main scientific article",
                "title_similarity": 0.95,
                "front_title_phrase_match": True,
            }
        ],
    }
    record = {
        "requested_doi": "10.1000/main",
        "observed_document_doi": "10.1000/correction",
        "relationship_type": "correction_record_to_original_doi",
        "identity_action": "accept_correction_original_doi",
        "record_group": "correction_record",
    }

    result = apply_identity_registry(identity, record, minimum_title_similarity=0.9)

    assert not result["verified"]
    assert result["registry_disposition"] == "unresolved_requested_title_is_not_correction"


def test_main_article_cannot_be_verified_by_its_correction() -> None:
    identity = {
        "status": "verified_related_doi",
        "verified": True,
        "requested_title": "Main scientific article",
        "document_title": "Correction: Main scientific article",
        "document_doi": "10.1000/correction",
    }

    result = reject_correction_artifact_for_main_record(identity)

    assert result["status"] == "main_article_points_to_correction"
    assert not result["verified"]


def test_correction_like_title_is_allowed_when_artifact_has_full_article_body() -> None:
    identity = {
        "status": "verified_exact_doi",
        "verified": True,
        "requested_title": "A Single Dose of 5-MeO-DMT Stimulates Cell Proliferation",
        "document_title": "Corrigendum: A Single Dose of 5-MeO-DMT Stimulates Cell Proliferation",
        "document_doi": "10.3389/fnmol.2018.00312",
    }
    artifact = {
        "extractions": [
            {
                "status": "ok",
                "char_count": 95000,
                "section_count": 19,
                "sections": [
                    {"heading": "Abstract"},
                    {"heading": "INTRODUCTION"},
                    {"heading": "Ethics Statement"},
                    {"heading": "Animals"},
                    {"heading": "5-MeO-DMT Treatment"},
                    {"heading": "BrdU Immunohistochemistry"},
                    {"heading": "RESULTS"},
                    {"heading": "DISCUSSION"},
                ],
            }
        ]
    }

    result = reject_correction_artifact_for_main_record(identity, artifact)

    assert result["status"] == "verified_exact_doi"
    assert result["verified"]
    assert result["correction_title_full_article_body_evidence"] is True


def test_correction_relationship_compares_title_after_correction_prefix() -> None:
    identity = {
        "status": "target_text_with_conflicting_doi",
        "verified": False,
        "requested_title": (
            "<i>Correction to:</i> Main scientific article by Doe, et al. "
            "Example Journal 2024;1:1-4"
        ),
        "evidence": [
            {
                "document_doi": "10.1000/main",
                "document_title": "Main scientific article",
                "title_similarity": 0.8,
                "title_coverage": 1.0,
                "title_phrase_match": False,
                "front_title_phrase_match": False,
            }
        ],
    }
    record = {
        "requested_doi": "10.1000/correction",
        "observed_document_doi": "10.1000/main",
        "relationship_type": "correction_record_to_original_doi",
        "identity_action": "accept_correction_original_doi",
        "record_group": "correction_record",
    }

    result = apply_identity_registry(identity, record, minimum_title_similarity=0.9)

    assert result["verified"]
    assert result["status"] == "verified_related_doi"
    assert result["registry_correction_title_similarity"] == 1.0


def test_audit_applies_registry_without_mutating_artifact(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "articles"
    artifact_dir.mkdir()
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
    artifact_path = artifact_dir / "10_1000_published.json"
    original = json.dumps(artifact, sort_keys=True)
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    registry = {
        "path": "test-registry.json",
        "version": 1,
        "minimum_front_title_similarity": 0.85,
        "records": {
            "10.1000/published": {
                "requested_doi": "10.1000/published",
                "observed_document_doi": "10.1000/preprint",
                "relationship_type": "preprint_repository_version",
                "identity_action": "accept_related_document_doi",
            }
        },
    }

    report = audit_artifacts(
        artifact_dir,
        {"10.1000/published": {"study_title": "Same scientific paper"}},
        identity_registry=registry,
    )

    assert report["counts"]["registry_applied"] == 1
    assert report["rows"][0]["identity_status"] == "verified_related_doi"
    assert report["rows"][0]["registry_applied"]
    assert json.dumps(json.loads(artifact_path.read_text(encoding="utf-8")), sort_keys=True) == original


def test_audit_does_not_promote_uncurated_metadata_relation(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "articles"
    artifact_dir.mkdir()
    tei = """
    <TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>
      <titleStmt><title>Same scientific paper</title></titleStmt>
      <sourceDesc><biblStruct><analytic><idno type="DOI">10.1000/commented-on</idno></analytic></biblStruct></sourceDesc>
    </fileDesc></teiHeader><text><body><p>Result.</p></body></text></TEI>
    """
    artifact = {
        "study_doi": "10.1000/comment",
        "study_title": "Same scientific paper",
        "best_backend": "grobid",
        "extractions": [extraction("grobid", tei, "tei_xml")],
    }
    (artifact_dir / "10_1000_comment.json").write_text(json.dumps(artifact), encoding="utf-8")
    metadata = {
        "10.1000/comment": {
            "study_title": "Same scientific paper",
            "publication_relations": "CommentOn doi: 10.1000/commented-on",
        }
    }

    report = audit_artifacts(artifact_dir, metadata)

    assert report["rows"][0]["identity_status"] == "target_text_with_conflicting_doi"
    assert not report["rows"][0]["identity_verified"]
