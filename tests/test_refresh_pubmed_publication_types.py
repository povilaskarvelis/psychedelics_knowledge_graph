import unittest
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import xml.etree.ElementTree as ET

import pandas as pd

from pipeline.ingest.refresh_pubmed_publication_types import (
    PubmedPublicationRecord,
    identity_text,
    main,
    parse_pubmed_publication_types,
    unique_pmids,
    update_publication_types,
)


class RefreshPubmedPublicationTypesTest(unittest.TestCase):
    def test_unique_pmids_preserves_order_and_skips_blanks(self) -> None:
        pmids = unique_pmids(pd.Series(["123", "", "123", "456", None]))

        self.assertEqual(pmids, ["123", "456"])

    def test_update_publication_types_replaces_generic_labels(self) -> None:
        df = pd.DataFrame(
            [
                {"doi": "10.example/review", "pmid": "123", "study_title": "Psychedelic treatment review", "publication_type": "journal-article", "language": "en"},
                {"doi": "10.example/primary", "pmid": "456", "study_title": "Primary ketamine trial", "publication_type": "Journal Article"},
                {"doi": "10.example/no-pmid", "pmid": "", "publication_type": "article"},
            ]
        )

        updated, updated_count = update_publication_types(
            df,
            {
                "123": PubmedPublicationRecord("123", "Psychedelic treatment review", ("10.example/review",), "Journal Article | Systematic Review | Meta-Analysis", languages=("eng",)),
                "456": PubmedPublicationRecord("456", "Primary ketamine trial", ("10.example/primary",), "Journal Article"),
            },
        )

        by_doi = {row["doi"]: row for row in updated.to_dict("records")}
        self.assertEqual(updated_count, 1)
        self.assertEqual(
            by_doi["10.example/review"]["publication_type"],
            "Journal Article | Systematic Review | Meta-Analysis",
        )
        self.assertEqual(by_doi["10.example/primary"]["publication_type"], "Journal Article")
        self.assertEqual(by_doi["10.example/no-pmid"]["publication_type"], "article")
        self.assertEqual(by_doi["10.example/review"]["language"], "en")

    def test_parser_retains_identity_language_and_xml_provenance(self) -> None:
        raw = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article>
        <ArticleTitle>Effects of <i>ketamine</i> on memory</ArticleTitle>
        <Abstract><AbstractText>Actual drug results.</AbstractText></Abstract><Language>eng</Language>
        <Journal><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
        <PublicationTypeList><PublicationType>Journal Article</PublicationType><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
        </Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1234/Example</ArticleId></ArticleIdList></PubmedData></PubmedArticle>
        <PubmedBookArticle><BookDocument><PMID>456</PMID></BookDocument></PubmedBookArticle></PubmedArticleSet>'''
        records = parse_pubmed_publication_types(raw)
        self.assertEqual(set(records), {"123"})  # Bookshelf is not automatically a book-chapter label.
        source = records["123"]
        self.assertEqual(source.title, "Effects of ketamine on memory")
        self.assertEqual(source.dois, ("10.1234/example",))
        self.assertEqual(source.languages, ("eng",))
        self.assertEqual(source.abstract, "Actual drug results.")
        self.assertEqual(len(source.source_xml_sha256), 64)
        self.assertIn("Randomized Controlled Trial", source.publication_type)
        with self.assertRaises(ET.ParseError):
            parse_pubmed_publication_types(b"<malformed")

    def test_shared_pmid_cannot_expand_scope_even_for_a_registered_alias(self) -> None:
        df = pd.DataFrame([
            {"doi": "10.1234/article", "pmid": "123", "study_title": "Actual ketamine trial", "publication_type": "article"},
            {"doi": "10.1234/alias", "pmid": "123", "study_title": "Actual ketamine trial", "publication_type": "article"},
        ])
        source = PubmedPublicationRecord("123", "Actual ketamine trial", ("10.1234/article",), "Journal Article | Clinical Trial")
        audit = []
        out, count = update_publication_types(df, {"123": source}, scoped_indices={0}, doi_aliases={"10.1234/alias": "10.1234/article"}, audit_rows=audit)
        self.assertEqual(count, 1)
        self.assertEqual(out.loc[1, "publication_type"], "article")
        self.assertEqual([row["doi"] for row in audit], ["10.1234/article"])
        out, count = update_publication_types(df, {"123": source}, scoped_indices={1}, doi_aliases={"10.1234/alias": "10.1234/article"})
        self.assertEqual(count, 1)
        self.assertEqual(out.loc[0, "publication_type"], "article")

    def test_conflicting_reports_are_not_relabelled_by_cached_pmid(self) -> None:
        cases = [
            ("source_doi_mismatch", "10.1234/published", "A suite of engineered psychedelic mice", "", "2026",
             PubmedPublicationRecord("123", "A suite of engineered psychedelic mice", ("10.1234/preprint",), "Preprint")),
            ("source_title_conflict", "10.1234/shared", "Subjective effects of MDMA on human sexual function", "", "2001",
             PubmedPublicationRecord("123", "Survey of patient satisfaction in adult psychiatric outpatient clinics", ("10.1234/shared",), "Journal Article")),
            ("source_abstract_conflict", "10.1234/shared", "MDMA sexual function study", "Sexual function in thirty-five recreational MDMA users was investigated. Desire and satisfaction were increased after MDMA use in actual participants.", "2001",
             PubmedPublicationRecord("123", "MDMA sexual function study", ("10.1234/shared",), "Journal Article", abstract="Psychiatric screening questionnaires were compared with diagnostic interviews in an Arab community. Sensitivity and specificity of screening instruments were estimated.")),
            ("source_year_conflict", "10.1234/report", "WHO Expert Committee on Drug Dependence", "", "1979",
             PubmedPublicationRecord("123", "WHO Expert Committee on Drug Dependence", ("10.1234/report",), "Technical Report", year="2006")),
            ("missing_source_doi_identity", "10.1234/report", "Actual ketamine trial", "", "2024",
             PubmedPublicationRecord("123", "Actual ketamine trial", (), "Journal Article")),
        ]
        for expected, doi, title, abstract, year, source in cases:
            with self.subTest(issue=expected):
                df = pd.DataFrame([{"doi": doi, "pmid": "123", "study_title": title, "abstract": abstract, "study_year": year, "publication_type": "article"}])
                audit = []
                out, count = update_publication_types(df, {"123": source}, audit_rows=audit)
                self.assertEqual(count, 0)
                pd.testing.assert_frame_equal(df, out)
                self.assertEqual(audit[0]["issue"], expected)

    def test_part_numbers_are_not_erased_and_subtitles_can_extend_titles(self) -> None:
        title = "Dose-response study of dimethyltryptamine in humans"
        source = PubmedPublicationRecord("123", title + ". I. Neuroendocrine effects", ("10.1234/part1",), "Journal Article")
        df = pd.DataFrame([{"doi": "10.1234/part1", "pmid": "123", "study_title": title, "publication_type": "article"}])
        _, count = update_publication_types(df, {"123": source})
        self.assertEqual(count, 1)
        df.loc[0, "study_title"] = title + ". II. Subjective effects"
        audit = []
        _, count = update_publication_types(df, {"123": source}, audit_rows=audit)
        self.assertEqual(count, 0)
        self.assertEqual(audit[0]["issue"], "source_title_conflict")

    def test_source_language_and_publication_version_conflicts_are_audited(self) -> None:
        df = pd.DataFrame([{"doi": "10.1234/article", "pmid": "123", "study_title": "Actual ketamine trial", "publication_type": "article", "language": "en"}])
        base = PubmedPublicationRecord("123", "Actual ketamine trial", ("10.1234/article",), "Journal Article")
        for source, expected in [
            (replace(base, languages=("ger",), publication_type="Journal Article | English Abstract"), "source_language_conflict_requires_version_review"),
            (replace(base, publication_type="Preprint"), "source_publication_format_conflict"),
        ]:
            audit = []
            out, count = update_publication_types(df, {"123": source}, audit_rows=audit)
            self.assertEqual(count, 0)
            pd.testing.assert_frame_equal(out, df)
            self.assertEqual(audit[0]["issue"], expected)
        df.loc[0, "publication_type"] = "conference abstract"
        audit = []
        _, count = update_publication_types(df, {"123": base}, audit_rows=audit)
        self.assertEqual(count, 0)
        self.assertEqual(audit[0]["issue"], "source_publication_format_conflict")

    def test_identity_text_preserves_scientific_comparisons(self) -> None:
        self.assertIn("eligible drug effect", identity_text("a<b and c>d; eligible drug effect <0.05 then >6.8"))
        self.assertEqual(identity_text("<i>Åsberg</i>"), identity_text("Asberg"))

    def test_cli_materializes_only_verified_requested_dois_and_never_empty_scope(self) -> None:
        module = "pipeline.ingest.refresh_pubmed_publication_types"
        for mismatched in [False, True]:
            with self.subTest(mismatched=mismatched), TemporaryDirectory() as temp:
                root = Path(temp)
                metadata = root / "metadata.parquet"
                report = root / "report.json"
                doi_file = root / "dois.txt"
                doi_file.write_text("10.1234/article\n")
                pd.DataFrame([
                    {"doi": "10.1234/article", "pmid": "123", "study_title": "Actual ketamine trial", "publication_type": "article"},
                    {"doi": "10.1234/alias", "pmid": "123", "study_title": "Actual ketamine trial", "publication_type": "article"},
                ]).to_parquet(metadata, index=False)
                source = PubmedPublicationRecord("123", "Actual ketamine trial", ("10.1234/wrong" if mismatched else "10.1234/article",), "Journal Article")
                argv = ["refresh", "--metadata-table", str(metadata), "--doi-file", str(doi_file), "--report-json", str(report)]
                with patch("sys.argv", argv), patch(module + ".load_config", return_value={}), patch(module + ".RateLimitedHttpClient"), patch(module + ".fetch_pubmed_publication_types", return_value={"123": source}), patch(module + ".load_doi_aliases", return_value={"10.1234/alias": "10.1234/article"}), patch(module + ".materialize_candidate_metadata", return_value={}) as materialize:
                    self.assertEqual(main(), 0)
                output = pd.read_parquet(metadata)
                self.assertEqual(output.loc[1, "publication_type"], "article")
                if mismatched:
                    materialize.assert_not_called()
                    self.assertEqual(output.loc[0, "publication_type"], "article")
                else:
                    self.assertEqual(materialize.call_args.kwargs["scoped_dois"], {"10.1234/article"})
                audit = json.loads(report.read_text())
                self.assertEqual(len(audit["rows"]), 1)
                self.assertEqual(audit["status"], "completed")

    def test_identity_audit_survives_candidate_materialization_failure(self) -> None:
        module = "pipeline.ingest.refresh_pubmed_publication_types"
        with TemporaryDirectory() as temp:
            root = Path(temp)
            metadata, report = root / "metadata.parquet", root / "report.json"
            pd.DataFrame([{"doi": "10.1234/article", "pmid": "123", "study_title": "Actual ketamine trial", "publication_type": "article"}]).to_parquet(metadata, index=False)
            source = PubmedPublicationRecord("123", "Actual ketamine trial", ("10.1234/article",), "Journal Article")
            with patch("sys.argv", ["refresh", "--metadata-table", str(metadata), "--report-json", str(report)]), patch(module + ".load_config", return_value={}), patch(module + ".RateLimitedHttpClient"), patch(module + ".fetch_pubmed_publication_types", return_value={"123": source}), patch(module + ".materialize_candidate_metadata", side_effect=RuntimeError("candidate write failed")):
                with self.assertRaisesRegex(RuntimeError, "candidate write failed"):
                    main()
            audit = json.loads(report.read_text())
            self.assertEqual(audit["status"], "prepared")
            self.assertEqual(audit["metadata_rows_written"], 1)
            self.assertEqual(audit["rows"][0]["status"], "identity_verified")


if __name__ == "__main__":
    unittest.main()
