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
            )

            lines = out_jsonl.read_text(encoding="utf-8").splitlines()
            saved_report = json.loads(report_json.read_text(encoding="utf-8"))

        self.assertEqual(report["counts"]["packets_written"], 1)
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["study_doi"], "10.1000/test")
        self.assertEqual(saved_report["counts"]["packets_written"], 1)

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

    def test_lean_primary_profile_keeps_methods_results_tables_and_mechanistic_other_sections(self) -> None:
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
            packet_profile="lean_primary",
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
        self.assertEqual(summary["packet_profile"], "lean_primary")
        self.assertGreater(summary["source_section_count"], summary["section_count"])
        self.assertGreater(summary["chunk_token_reduction_estimate"], 0)

    def test_lean_primary_profile_keeps_only_abstract_for_secondary_literature(self) -> None:
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
            packet_profile="lean_primary",
        )

        self.assertEqual([section["heading"] for section in packet["sections"]], ["Abstract"])
        self.assertEqual(packet["tables"], [])
        self.assertEqual(packet["figures"], [])
        self.assertEqual(packet["references"], [])
        self.assertEqual(
            packet["document_summary"]["profile_summary"]["section_selection"],
            "secondary_or_context_abstract_only",
        )


if __name__ == "__main__":
    unittest.main()
