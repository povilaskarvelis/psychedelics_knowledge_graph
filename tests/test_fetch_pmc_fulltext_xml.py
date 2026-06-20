import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.fulltext.fetch_pmc_fulltext_xml import (
    build_xml_artifact,
    pmcid_from_metadata,
    sections_from_jats,
    selected_rows,
)
from pipeline.fulltext.convert_pdfs import doi_to_slug


JATS_XML = """
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <article-title>Example Europe PMC XML paper</article-title>
      <abstract id="abs1"><p>This article studies psilocybin and brain networks.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec id="s1">
      <title>Methods</title>
      <p>Functional connectivity was measured after psilocybin exposure.</p>
      <sec id="s2">
        <title>Results</title>
        <p>Default mode network connectivity changed after treatment.</p>
      </sec>
    </sec>
  </body>
</article>
"""


class FetchPmcFulltextXmlTest(unittest.TestCase):
    def test_sections_from_jats_extracts_abstract_and_nested_sections(self) -> None:
        sections = sections_from_jats(JATS_XML)

        self.assertEqual([section["heading"] for section in sections], ["Abstract", "Methods", "Results"])
        self.assertIn("psilocybin", sections[0]["snippet"])
        self.assertIn("Functional connectivity", sections[1]["snippet"])
        self.assertIn("Default mode network", sections[2]["snippet"])
        self.assertEqual(sections[1]["xml_id"], "s1")

    def test_build_xml_artifact_uses_fulltext_artifact_shape(self) -> None:
        artifact = build_xml_artifact(
            {"doi": "10.1000/xml", "study_title": "", "study_year": "2025"},
            pmcid="PMC123456",
            endpoint=(
                "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
                "?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:123456&metadataPrefix=pmc"
            ),
            xml_text=JATS_XML,
            retrieval_source="pmc_oai_xml",
            retrieval_trace=[{"source": "pmc_oai_xml", "status": "ok", "error": ""}],
        )

        self.assertEqual(artifact["dataset"], "articles")
        self.assertEqual(artifact["fulltext_artifact_layout"], "canonical_articles_v1")
        self.assertEqual(artifact["study_doi"], "10.1000/xml")
        self.assertEqual(artifact["study_title"], "Example Europe PMC XML paper")
        self.assertEqual(artifact["pdf_local_path"], "")
        self.assertEqual(artifact["fulltext_source"], "pmc_oai_xml")
        self.assertEqual(artifact["pmcid"], "PMC123456")
        self.assertEqual(artifact["best_backend"], "pmc_oai_xml")
        self.assertGreater(artifact["best_char_count"], 0)
        self.assertEqual(artifact["extractions"][0]["metadata"]["format"], "jats_xml")
        self.assertEqual(artifact["retrieval_trace"][0]["source"], "pmc_oai_xml")

    def test_pmcid_from_metadata_accepts_field_or_candidate_urls(self) -> None:
        self.assertEqual(pmcid_from_metadata({"pmcid": "pmc123"}), "PMC123")
        self.assertEqual(
            pmcid_from_metadata({"pdf_url_candidates": "https://pmc.ncbi.nlm.nih.gov/articles/PMC456/pdf/example.pdf"}),
            "PMC456",
        )

    def test_selected_rows_skips_existing_fulltext_and_local_pdf_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fulltext_dir = root / "fulltext"
            pdf_root = root / "pdfs"
            existing_doi = "10.1000/existing"
            pdf_doi = "10.1000/local-pdf"
            target_doi = "10.1000/target"

            existing_artifact = fulltext_dir / "articles" / f"{doi_to_slug(existing_doi)}.json"
            existing_artifact.parent.mkdir(parents=True)
            existing_artifact.write_text(json.dumps({"best_char_count": 123}), encoding="utf-8")

            pdf_path = pdf_root / f"{doi_to_slug(pdf_doi)}__abc123.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.4\n")

            routes_df = pd.DataFrame(
                [
                    {"doi": existing_doi, "retained_for_extraction_candidate": True},
                    {"doi": pdf_doi, "retained_for_extraction_candidate": True},
                    {"doi": target_doi, "retained_for_extraction_candidate": True},
                    {"doi": "10.1000/not-retained", "retained_for_extraction_candidate": False},
                ]
            )
            metadata_df = pd.DataFrame(
                [
                    {"doi": existing_doi, "pmcid": "PMC1"},
                    {"doi": pdf_doi, "pmcid": "PMC2"},
                    {"doi": target_doi, "pmcid": "PMC3"},
                    {"doi": "10.1000/not-retained", "pmcid": "PMC4"},
                ]
            )

            rows, skipped = selected_rows(
                routes_df=routes_df,
                metadata_df=metadata_df,
                fulltext_dir=fulltext_dir,
                paper_root=pdf_root,
                doi_filter=None,
                include_existing_fulltext=False,
                include_local_pdf=False,
                include_non_retained=False,
            )

        self.assertEqual([row["doi"] for row in rows], [target_doi])
        self.assertEqual(skipped["existing_fulltext"], 1)
        self.assertEqual(skipped["local_pdf_available"], 1)
        self.assertEqual(skipped["not_retained"], 1)


if __name__ == "__main__":
    unittest.main()
