import json
import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.build_llm_evidence_packets import (
    build_dataset_packets,
    build_llm_chunks,
    build_packet,
    extract_references,
    extract_tables_and_figures,
    sections_from_tei_full,
)


def write_source_identity_audit(root: Path, rows: list[dict]) -> Path:
    identity_registry = root / "source_identity_registry.json"
    hash_registry = root / "source_identity_pdf_hash_registry.json"
    identity_registry.write_text("{}\n", encoding="utf-8")
    hash_registry.write_text("{}\n", encoding="utf-8")
    audit = root / "source_identity_audit.json"
    audit.write_text(
        json.dumps(
            {
                "identity_registry": {"path": str(identity_registry)},
                "pdf_hash_attestation_registry": {"path": str(hash_registry)},
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )
    return audit


TEI = """
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text>
    <front>
      <abstract xml:id="abs1"><p>This randomized trial enrolled 40 participants.</p></abstract>
    </front>
    <body>
      <div xml:id="sec1">
        <head>Methods</head>
        <p>Participants received psilocybin or placebo for eight weeks.</p>
        <figure type="table" xml:id="tab1">
          <head>Table 1</head>
          <figDesc>Baseline clinical characteristics.</figDesc>
          <table><row><cell>Arm</cell><cell>N</cell></row></table>
        </figure>
        <div xml:id="sec2">
          <head>Results</head>
          <p>Depression scores improved more with psilocybin than placebo.</p>
        </div>
      </div>
      <figure xml:id="fig1">
        <head>Figure 1</head>
        <figDesc>Change in depression scores.</figDesc>
      </figure>
    </body>
    <back>
      <listBibl>
        <biblStruct xml:id="ref1">
          <analytic><title>Prior trial</title></analytic>
          <idno type="DOI">10.1000/ref</idno>
          <monogr><imprint><date when="2020"/></imprint></monogr>
        </biblStruct>
      </listBibl>
    </back>
  </text>
</TEI>
"""

LEAN_TEI = """
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text>
    <front>
      <abstract><p>LSD binding and functional activity were measured in vitro.</p></abstract>
    </front>
    <body>
      <div><head>Introduction</head><p>Background about psychedelic pharmacology.</p></div>
      <div><head>Methods</head><p>Radioligand assays used cloned serotonin receptors.</p></div>
      <div><head>Pharmacological Characterization</head><p>LSD bound 5-HT2A with high affinity.</p></div>
      <div><head>Results</head><p>Functional activity was observed at 5-HT2A receptors.</p></div>
      <div><head>Discussion</head><p>The broader interpretation is discussed here.</p></div>
      <figure type="table"><head>Table 1</head><figDesc>Binding affinity results.</figDesc><table><row><cell>Ki</cell></row></table></figure>
      <figure><head>Figure 1</head><figDesc>Binding assay response curve.</figDesc></figure>
      <figure><head>Figure 2</head><figDesc>Conceptual overview.</figDesc></figure>
    </body>
    <back>
      <listBibl>
        <biblStruct><analytic><title>Background review</title></analytic></biblStruct>
      </listBibl>
    </back>
  </text>
</TEI>
"""

SYNTHESIS_TEI = """
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text>
    <front>
      <abstract><p>This meta-analysis pooled randomized trials of psilocybin for depression.</p></abstract>
    </front>
    <body>
      <div><head>Introduction</head><p>Background about psychedelic therapy.</p></div>
      <div><head>Search Strategy</head><p>MEDLINE and PsycINFO were searched for eligible trials.</p></div>
      <div><head>Risk of Bias</head><p>Two reviewers assessed risk of bias using RoB 2.</p></div>
      <div><head>Results</head><p>The pooled standardized mean difference favored psilocybin.</p></div>
      <div><head>Limitations</head><p>Certainty was downgraded for small study effects.</p></div>
      <figure type="table"><head>Table 1</head><figDesc>Included study characteristics.</figDesc><table><row><cell>Trial</cell></row></table></figure>
      <figure><head>Figure 1</head><figDesc>Forest plot for depressive symptoms.</figDesc></figure>
    </body>
    <back>
      <listBibl>
        <biblStruct><analytic><title>Included trial</title></analytic><idno type="DOI">10.1000/trial</idno></biblStruct>
      </listBibl>
    </back>
  </text>
</TEI>
"""

REVIEW_TEI = """
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text>
    <front>
      <abstract><p>This review summarizes mechanisms and safety findings for psychedelics.</p></abstract>
    </front>
    <body>
      <div><head>Scope and Objectives</head><p>The review covers human and preclinical evidence.</p></div>
      <div><head>Clinical Evidence</head><p>Trials and observational studies are summarized.</p></div>
      <div><head>Future Directions</head><p>Evidence gaps include dose-response uncertainty.</p></div>
      <div><head>Funding</head><p>Supported by a grant.</p></div>
      <figure type="table"><head>Table 1</head><figDesc>Evidence coverage by domain.</figDesc><table><row><cell>Domain</cell></row></table></figure>
    </body>
    <back>
      <listBibl>
        <biblStruct><analytic><title>Background source</title></analytic><idno type="DOI">10.1000/background</idno></biblStruct>
      </listBibl>
    </back>
  </text>
</TEI>
"""

JATS_XML = """
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <abstract id="abs1"><p>This open-access article reports psilocybin outcomes.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec id="s1">
      <title>Methods</title>
      <p>Participants received psilocybin-assisted therapy.</p>
      <sec id="s2">
        <title>Results</title>
        <p>Depressive symptoms decreased after treatment.</p>
      </sec>
    </sec>
  </body>
</article>
"""


class BuildLlmEvidencePacketsTest(unittest.TestCase):
    def test_sections_from_tei_full_reconstructs_complete_nested_sections(self) -> None:
        sections = sections_from_tei_full(TEI)

        self.assertEqual([section["heading"] for section in sections], ["Abstract", "Methods", "Results"])
        self.assertIn("40 participants", sections[0]["text"])
        self.assertIn("psilocybin or placebo", sections[1]["text"])
        self.assertNotIn("Depression scores improved", sections[1]["text"])
        self.assertIn("Depression scores improved", sections[2]["text"])
        self.assertEqual(sections[0]["section_id"], "S001")
        self.assertLess(sections[0]["char_start"], sections[1]["char_start"])

    def test_sections_from_tei_full_accepts_jats_sec_title_structure(self) -> None:
        sections = sections_from_tei_full(JATS_XML)

        self.assertEqual([section["heading"] for section in sections], ["Abstract", "Methods", "Results"])
        self.assertIn("open-access article", sections[0]["text"])
        self.assertIn("psilocybin-assisted therapy", sections[1]["text"])
        self.assertNotIn("Depressive symptoms decreased", sections[1]["text"])
        self.assertIn("Depressive symptoms decreased", sections[2]["text"])
        self.assertEqual(sections[1]["xml_id"], "s1")

    def test_extract_tables_figures_and_references(self) -> None:
        tables, figures = extract_tables_and_figures(TEI)
        refs = extract_references(TEI)

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["table_id"], "T001")
        self.assertEqual(tables[0]["section_heading"], "Methods")
        self.assertIn("Baseline clinical", tables[0]["caption"])
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["figure_id"], "F001")
        self.assertEqual(refs[0]["title"], "Prior trial")
        self.assertEqual(refs[0]["doi"], "10.1000/ref")

    def test_build_llm_chunks_records_section_and_document_offsets(self) -> None:
        sections = sections_from_tei_full(TEI)
        chunks = build_llm_chunks(sections, max_chunk_chars=50, overlap_chars=10)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["chunk_id"], "C001")
        self.assertEqual(chunks[0]["section_id"], "S001")
        self.assertEqual(chunks[0]["document_char_start"], sections[0]["char_start"])
        self.assertIn("participants", chunks[0]["text"])

    def test_build_packet_includes_metadata_contexts_and_source_hints(self) -> None:
        artifact = {
            "study_doi": "10.1000/test",
            "study_title": "Example review",
            "study_year": "2024",
            "pdf_local_path": "/tmp/test.pdf",
            "best_backend": "grobid",
            "best_char_count": len(TEI),
            "best_section_count": 3,
            "extractions": [
                {
                    "backend": "grobid",
                    "status": "ok",
                    "text": TEI,
                    "metadata": {"format": "tei_xml"},
                }
            ],
        }
        row = {
            "study_doi": "10.1000/test",
            "study_title": "Example review",
            "study_journal": "Journal of Tests",
            "publication_type": "Journal Article | Systematic Review",
            "trial_registry_ids": "NCT12345678",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }

        packet = build_packet(
            "disorder",
            Path("/tmp/artifact.json"),
            artifact,
            row,
            max_chunk_chars=80,
            overlap_chars=10,
            max_chunks_per_paper=0,
            max_references=50,
        )

        self.assertEqual(packet["schema_version"], "llm_evidence_packet_v1")
        self.assertEqual(packet["paper_metadata"]["study_journal"], "Journal of Tests")
        self.assertEqual(packet["source_hints"]["source_family_hint"], "evidence_synthesis")
        self.assertEqual(packet["candidate_contexts"][0]["compound"], "Psilocybin")
        self.assertEqual(packet["document_summary"]["table_count"], 1)
        self.assertGreater(packet["document_summary"]["chunk_count"], 0)

    def test_build_dataset_packets_writes_jsonl_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "artifacts"
            artifact_dir.mkdir()
            artifact_path = artifact_dir / "10_1000_test.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "study_doi": "10.1000/test",
                        "study_title": "Example",
                        "best_backend": "grobid",
                        "best_char_count": len(TEI),
                        "best_section_count": 3,
                        "source_identity": {"status": "verified_exact_doi"},
                        "extractions": [{"backend": "grobid", "status": "ok", "text": TEI, "metadata": {"format": "tei_xml"}}],
                    }
                ),
                encoding="utf-8",
            )
            paper_library = root / "paper_library.json"
            paper_library.write_text(
                json.dumps([{"study_doi": "10.1000/test", "study_title": "Example", "publication_type": "journal-article"}]),
                encoding="utf-8",
            )
            out_jsonl = root / "packets.jsonl"
            report_json = root / "report.json"
            source_identity_audit = write_source_identity_audit(
                root,
                [
                    {
                        "requested_doi": "10.1000/test",
                        "artifact_path": str(artifact_path.resolve()),
                        "identity_verified": True,
                    }
                ],
            )

            report = build_dataset_packets(
                "mechanistic",
                paper_library=paper_library,
                artifact_dir=artifact_dir,
                out_jsonl=out_jsonl,
                report_json=report_json,
                doi_filter=None,
                limit=0,
                max_chunk_chars=100,
                overlap_chars=10,
                max_chunks_per_paper=0,
                max_references=10,
                include_section_text=True,
                include_candidate_contexts=True,
                source_identity_audit=source_identity_audit,
            )

            lines = out_jsonl.read_text(encoding="utf-8").splitlines()
            saved_report = json.loads(report_json.read_text(encoding="utf-8"))

        self.assertEqual(report["counts"]["packets_written"], 1)
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["study_doi"], "10.1000/test")
        self.assertEqual(saved_report["counts"]["packets_written"], 1)

    def test_build_dataset_packets_refuses_nonpassing_identity_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "artifacts"
            artifact_dir.mkdir()
            (artifact_dir / "10_1000_test.json").write_text(
                json.dumps(
                    {
                        "study_doi": "10.1000/test",
                        "best_backend": "grobid",
                        "best_char_count": len(TEI),
                        "extractions": [
                            {
                                "backend": "grobid",
                                "status": "ok",
                                "text": TEI,
                                "metadata": {"format": "tei_xml"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            paper_library = root / "paper_library.json"
            paper_library.write_text(
                json.dumps([{"study_doi": "10.1000/test"}]),
                encoding="utf-8",
            )
            out_jsonl = root / "packets.jsonl"
            source_identity_audit = write_source_identity_audit(
                root,
                [
                    {
                        "requested_doi": "10.1000/test",
                        "artifact_path": str((artifact_dir / "10_1000_test.json").resolve()),
                        "identity_verified": False,
                    }
                ],
            )

            with self.assertRaisesRegex(RuntimeError, "audit is not passing"):
                build_dataset_packets(
                    "mechanistic",
                    paper_library=paper_library,
                    artifact_dir=artifact_dir,
                    out_jsonl=out_jsonl,
                    report_json=root / "report.json",
                    doi_filter=None,
                    limit=0,
                    max_chunk_chars=100,
                    overlap_chars=10,
                    max_chunks_per_paper=0,
                    max_references=10,
                    include_section_text=True,
                    include_candidate_contexts=True,
                    source_identity_audit=source_identity_audit,
                )

            self.assertFalse(out_jsonl.exists())

    def test_build_packet_can_omit_candidate_context_hints(self) -> None:
        artifact = {
            "study_doi": "10.1000/test",
            "study_title": "Example review",
            "best_backend": "grobid",
            "best_char_count": len(TEI),
            "best_section_count": 3,
            "extractions": [
                {
                    "backend": "grobid",
                    "status": "ok",
                    "text": TEI,
                    "metadata": {"format": "tei_xml"},
                }
            ],
        }
        row = {
            "study_doi": "10.1000/test",
            "study_title": "Example review",
            "publication_type": "Journal Article",
            "contexts": [{"compound": "Legacy", "entity": "Context"}],
        }

        packet = build_packet(
            "mechanistic",
            Path("/tmp/artifact.json"),
            artifact,
            row,
            max_chunk_chars=80,
            overlap_chars=10,
            max_chunks_per_paper=0,
            max_references=10,
            include_section_text=True,
            include_candidate_contexts=False,
        )

        self.assertEqual(packet["candidate_contexts"], [])

    def test_primary_empirical_profile_keeps_methods_results_tables_and_mechanistic_other_sections(self) -> None:
        artifact = {
            "study_doi": "10.1000/lean",
            "study_title": "Mechanistic example",
            "best_backend": "grobid",
            "best_char_count": len(LEAN_TEI),
            "best_section_count": 5,
            "extractions": [{"backend": "grobid", "status": "ok", "text": LEAN_TEI, "metadata": {"format": "tei_xml"}}],
        }
        row = {"study_doi": "10.1000/lean", "study_title": "Mechanistic example", "publication_type": "Journal Article"}

        packet = build_packet(
            "mechanistic",
            Path("/tmp/lean.json"),
            artifact,
            row,
            max_chunk_chars=500,
            overlap_chars=0,
            max_chunks_per_paper=0,
            max_references=50,
            packet_profile="primary_empirical",
        )

        headings = [section["heading"] for section in packet["sections"]]
        self.assertIn("Abstract", headings)
        self.assertIn("Methods", headings)
        self.assertIn("Pharmacological Characterization", headings)
        self.assertIn("Results", headings)
        self.assertNotIn("Introduction", headings)
        self.assertNotIn("Discussion", headings)
        self.assertEqual(len(packet["tables"]), 1)
        self.assertEqual(len(packet["figures"]), 1)
        self.assertEqual(packet["references"], [])
        summary = packet["document_summary"]
        self.assertEqual(summary["packet_profile"], "primary_empirical")
        self.assertGreater(summary["source_section_count"], summary["section_count"])
        self.assertGreater(summary["chunk_token_reduction_estimate"], 0)

    def test_primary_empirical_legacy_alias_normalizes_to_canonical_profile(self) -> None:
        artifact = {
            "study_doi": "10.1000/legacy-lean",
            "study_title": "Mechanistic example",
            "best_backend": "grobid",
            "best_char_count": len(LEAN_TEI),
            "best_section_count": 5,
            "extractions": [{"backend": "grobid", "status": "ok", "text": LEAN_TEI, "metadata": {"format": "tei_xml"}}],
        }
        row = {"study_doi": "10.1000/legacy-lean", "study_title": "Mechanistic example", "publication_type": "Journal Article"}

        packet = build_packet(
            "mechanistic",
            Path("/tmp/legacy_lean.json"),
            artifact,
            row,
            max_chunk_chars=500,
            overlap_chars=0,
            max_chunks_per_paper=0,
            max_references=50,
            packet_profile="lean_primary",
        )

        self.assertEqual(packet["packet_profile"], "primary_empirical")
        self.assertEqual(packet["requested_packet_profile"], "lean_primary")
        self.assertEqual(packet["document_summary"]["packet_profile"], "primary_empirical")

    def test_primary_study_section_selection_alias_normalizes_to_canonical_profile(self) -> None:
        artifact = {
            "study_doi": "10.1000/primary-strategy",
            "study_title": "Mechanistic example",
            "best_backend": "grobid",
            "best_char_count": len(LEAN_TEI),
            "best_section_count": 5,
            "extractions": [{"backend": "grobid", "status": "ok", "text": LEAN_TEI, "metadata": {"format": "tei_xml"}}],
        }
        row = {
            "study_doi": "10.1000/primary-strategy",
            "study_title": "Mechanistic example",
            "publication_type": "Journal Article",
        }

        packet = build_packet(
            "mechanistic",
            Path("/tmp/primary_strategy.json"),
            artifact,
            row,
            max_chunk_chars=500,
            overlap_chars=0,
            max_chunks_per_paper=0,
            max_references=50,
            packet_profile="primary_study",
        )

        self.assertEqual(packet["packet_profile"], "primary_empirical")
        self.assertEqual(packet["requested_packet_profile"], "primary_study")
        self.assertEqual(packet["document_summary"]["packet_profile"], "primary_empirical")

    def test_primary_empirical_profile_keeps_only_abstract_for_secondary_literature(self) -> None:
        artifact = {
            "study_doi": "10.1000/review",
            "study_title": "Review example",
            "best_backend": "grobid",
            "best_char_count": len(LEAN_TEI),
            "best_section_count": 5,
            "extractions": [{"backend": "grobid", "status": "ok", "text": LEAN_TEI, "metadata": {"format": "tei_xml"}}],
        }
        row = {
            "study_doi": "10.1000/review",
            "study_title": "Review example",
            "publication_type": "Journal Article | Systematic Review",
        }

        packet = build_packet(
            "disorder",
            Path("/tmp/review.json"),
            artifact,
            row,
            max_chunk_chars=500,
            overlap_chars=0,
            max_chunks_per_paper=0,
            max_references=50,
            packet_profile="primary_empirical",
        )

        self.assertEqual([section["heading"] for section in packet["sections"]], ["Abstract"])
        self.assertEqual(packet["tables"], [])
        self.assertEqual(packet["figures"], [])
        self.assertEqual(packet["references"], [])
        self.assertEqual(
            packet["document_summary"]["profile_summary"]["section_selection"],
            "secondary_or_context_abstract_only",
        )

    def test_secondary_synthesis_profile_keeps_meta_analysis_details_and_references(self) -> None:
        artifact = {
            "study_doi": "10.1000/meta",
            "study_title": "Meta-analysis example",
            "best_backend": "grobid",
            "best_char_count": len(SYNTHESIS_TEI),
            "best_section_count": 5,
            "extractions": [{"backend": "grobid", "status": "ok", "text": SYNTHESIS_TEI, "metadata": {"format": "tei_xml"}}],
        }
        row = {
            "study_doi": "10.1000/meta",
            "study_title": "Meta-analysis example",
            "publication_type": "Journal Article | Meta-Analysis",
        }

        packet = build_packet(
            "disorder",
            Path("/tmp/meta.json"),
            artifact,
            row,
            max_chunk_chars=500,
            overlap_chars=0,
            max_chunks_per_paper=0,
            max_references=50,
            packet_profile="secondary_synthesis",
        )

        headings = [section["heading"] for section in packet["sections"]]
        self.assertIn("Search Strategy", headings)
        self.assertIn("Risk of Bias", headings)
        self.assertIn("Results", headings)
        self.assertIn("Limitations", headings)
        self.assertNotIn("Introduction", headings)
        self.assertEqual(len(packet["tables"]), 1)
        self.assertEqual(len(packet["figures"]), 1)
        self.assertEqual(packet["references"][0]["doi"], "10.1000/trial")
        self.assertEqual(packet["packet_profile"], "secondary_synthesis")
        self.assertEqual(packet["document_summary"]["profile_summary"]["section_selection"], "secondary_synthesis")

    def test_review_coverage_profile_keeps_review_scope_and_omits_references(self) -> None:
        artifact = {
            "study_doi": "10.1000/review-coverage",
            "study_title": "Review coverage example",
            "best_backend": "grobid",
            "best_char_count": len(REVIEW_TEI),
            "best_section_count": 4,
            "extractions": [{"backend": "grobid", "status": "ok", "text": REVIEW_TEI, "metadata": {"format": "tei_xml"}}],
        }
        row = {
            "study_doi": "10.1000/review-coverage",
            "study_title": "Review coverage example",
            "publication_type": "Journal Article | Review",
        }

        packet = build_packet(
            "mechanistic",
            Path("/tmp/review_coverage.json"),
            artifact,
            row,
            max_chunk_chars=500,
            overlap_chars=0,
            max_chunks_per_paper=0,
            max_references=50,
            packet_profile="review_coverage",
        )

        headings = [section["heading"] for section in packet["sections"]]
        self.assertIn("Scope and Objectives", headings)
        self.assertIn("Clinical Evidence", headings)
        self.assertIn("Future Directions", headings)
        self.assertNotIn("Funding", headings)
        self.assertEqual(len(packet["tables"]), 1)
        self.assertEqual(packet["references"], [])
        self.assertEqual(packet["document_summary"]["profile_summary"]["section_selection"], "review_coverage")


if __name__ == "__main__":
    unittest.main()
