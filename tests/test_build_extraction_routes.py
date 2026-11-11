import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tests.identity_fixtures import write_gate_table
from pipeline.extract.build_extraction_routes import (
    build_candidate_status_updates,
    build_extraction_routes,
    build_route_rows,
    carry_screening_from_merged_dois,
    doi_to_slug,
    fulltext_status_for_doi,
    merged_extraction_metadata,
    preserve_out_of_scope_route_selection,
    prescreen_context_by_doi,
    thesis_or_dissertation_flags,
)


class BuildExtractionRoutesTests(unittest.TestCase):
    def test_source_hold_never_inherits_an_included_model_route(self) -> None:
        from pipeline.extract.build_extraction_routes import route_status_for_candidate

        doi = "10.1000/unresolved-report"
        for family in ("primary", "secondary_literature"):
            with self.subTest(family=family):
                metadata = pd.DataFrame([{"doi": doi, "study_title": "Conflicting report",
                                          "abstract": "An available abstract.", "publication_type": "Journal Article"}])
                prescreen = pd.DataFrame([{"doi": doi, "prescreen_decision": "retain",
                                           "retained_for_extraction_candidate": True}])
                literature = pd.DataFrame([{"doi": doi, "source_family": family,
                                            "primary_secondary_source_type": "review" if family == "secondary_literature" else "primary",
                                            "retained_for_extraction_candidate": True}])
                domain = pd.DataFrame([{"doi": doi, "domain_route": "clinical_outcome",
                                        "screening_decision": "include_in_scope", "model": "gpt-6-luna"}])
                original = domain.copy(deep=True)
                rows = build_route_rows(metadata, prescreen, literature, domain,
                    fulltext_dir=Path("/tmp/nonexistent-source-hold"), generated_at_utc="2026-10-22",
                    manual_overrides={doi: {"manual_action": "hold_source_review",
                                            "manual_reason": "Report identity is not established."}})
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["route_action"], "hold_source_review")
                self.assertFalse(rows[0]["retained_for_extraction_candidate"])
                self.assertTrue(rows[0]["domain_needs_human_review"])
                status, _, retained = route_status_for_candidate(route_rows=rows, prescreen_retained=True)
                self.assertEqual(status, "hold_source_review")
                self.assertFalse(retained)
                pd.testing.assert_frame_equal(domain, original)

    def screening_inputs(self) -> dict:
        def domain(decision: str, route: str = "molecular_target") -> list[dict]:
            return [{"screening_decision": decision, "domain_route": route}]

        return {
            "prescreen": {
                "10.1000/in": {"retained": True},
                "10.1000/out": {"retained": True},
                "10.1000/no-prescreen-kept": {"retained": False},
                "10.1000/in-2": {"retained": True},
                "10.1000/both-in": {"retained": True},
                "10.1000/both-in-merged": {"retained": True},
            },
            "prescreen_dois": {
                "10.1000/in",
                "10.1000/out",
                "10.1000/no-prescreen-kept",
                "10.1000/in-2",
                "10.1000/both-in",
                "10.1000/both-in-merged",
            },
            "literature_by_doi": {"10.1000/in": {"source_family": "primary"}},
            "domain_by_doi": {
                "10.1000/in": domain("include_in_scope"),
                "10.1000/out": domain("exclude_out_of_scope", ""),
                "10.1000/in-2": domain("include_in_scope", "brain_system"),
                "10.1000/both-in": domain("include_in_scope", "clinical_outcome"),
                "10.1000/both-in-merged": domain("include_in_scope", "safety_tolerability"),
            },
            "screening_overrides": {},
        }

    def test_kept_doi_takes_screening_result_of_included_merged_doi(self) -> None:
        inputs = self.screening_inputs()
        carried = carry_screening_from_merged_dois(
            {
                "10.1000/in": "10.1000/out",
                "10.1000/in-2": "10.1000/no-prescreen-kept",
                "10.1000/both-in-merged": "10.1000/both-in",
            },
            **inputs,
        )
        self.assertEqual(
            carried,
            {"10.1000/out": "10.1000/in", "10.1000/no-prescreen-kept": "10.1000/in-2"},
        )
        self.assertEqual(inputs["domain_by_doi"]["10.1000/out"][0]["screening_decision"], "include_in_scope")
        self.assertEqual(inputs["literature_by_doi"]["10.1000/out"], {"source_family": "primary"})
        self.assertTrue(inputs["prescreen"]["10.1000/no-prescreen-kept"]["retained"])
        self.assertEqual(inputs["domain_by_doi"]["10.1000/both-in"][0]["domain_route"], "clinical_outcome")

    def test_ledger_records_the_screening_result_a_kept_doi_was_selected_on(self) -> None:
        kept, merged = "10.1097/00000539-200210000-00071", "10.1213/00000539-200210000-00071"
        prescreen_df = pd.DataFrame([
            {"doi": kept, "prescreen_decision": "exclude", "prescreen_action": "exclude_non_evidence_artifact"},
            {"doi": merged, "prescreen_decision": "retain", "prescreen_action": "retain_for_extraction"},
        ])
        route = {"doi": kept, "retained_for_extraction_candidate": True, "route_action": "extract_from_abstract_only",
                 "domain_route": "safety_tolerability", "domain_screening_decision": "include_in_scope"}
        updates = build_candidate_status_updates(
            candidate_df=pd.DataFrame([{"doi": kept}, {"doi": merged}]), prescreen_df=prescreen_df,
            route_rows=[route], generated_at_utc="2026-11-08T00:00:00+00:00", doi_aliases={merged: kept},
        )
        row = updates.set_index("doi").loc[kept]
        self.assertTrue(row["retained_for_extraction_candidate"])
        self.assertTrue(row["prescreen_retained_for_extraction_candidate"])
        self.assertEqual(row["prescreen_actions"], "retain_for_extraction")
        self.assertIn(f"Screening result of {merged}", row["prescreen_reasons"])

    def test_excluded_merged_doi_and_curated_exclusion_carry_nothing(self) -> None:
        inputs = self.screening_inputs()
        self.assertEqual(
            carry_screening_from_merged_dois({"10.1000/out": "10.1000/in"}, **inputs),
            {},
        )
        inputs = self.screening_inputs()
        inputs["screening_overrides"] = {"10.1000/in": {"decision": "exclude_out_of_scope", "reason": "reviewed"}}
        self.assertEqual(
            carry_screening_from_merged_dois({"10.1000/in": "10.1000/out"}, **inputs),
            {},
        )

    def test_scoped_full_rebuild_preserves_out_of_scope_selection_state(self) -> None:
        candidates = pd.DataFrame(
            [
                {"doi": "10.1000/in-scope", "retained_for_extraction_candidate": False},
                {"doi": "10.1000/selected", "retained_for_extraction_candidate": True},
                {"doi": "10.1000/backlog", "retained_for_extraction_candidate": False},
            ]
        )
        rows = [
            {"doi": "10.1000/in-scope", "retained_for_extraction_candidate": True},
            {"doi": "10.1000/selected", "retained_for_extraction_candidate": True},
            {"doi": "10.1000/backlog", "retained_for_extraction_candidate": True},
        ]

        preserved = preserve_out_of_scope_route_selection(
            rows,
            candidate_df=candidates,
            scoped_dois={"10.1000/in-scope"},
        )

        by_doi = {row["doi"]: row for row in preserved}
        self.assertTrue(by_doi["10.1000/in-scope"]["retained_for_extraction_candidate"])
        self.assertTrue(by_doi["10.1000/selected"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.1000/backlog"]["retained_for_extraction_candidate"])

    def test_thesis_url_does_not_override_explicit_journal_article(self) -> None:
        self.assertEqual(
            thesis_or_dissertation_flags(
                {
                    "doi": "10.3109/example",
                    "publication_type": "Journal Article",
                    "study_journal": "International Journal",
                    "open_access_url": "https://figshare.com/articles/thesis/same_title/123",
                }
            ),
            "",
        )

    def test_thesis_doi_is_detected_without_access_url(self) -> None:
        self.assertIn(
            "thesis_or_dissertation_doi",
            thesis_or_dissertation_flags(
                {
                    "doi": "10.25365/thesis.46291",
                    "publication_type": "article",
                    "study_journal": "University of Vienna",
                }
            ),
        )

    def test_blank_string_enrichment_does_not_erase_candidate_abstract(self) -> None:
        candidate = pd.DataFrame(
            {
                "doi": pd.Series(["10.1000/blank-enrichment"], dtype="string"),
                "study_title": pd.Series(["Candidate title"], dtype="string"),
                "abstract": pd.Series(["A usable candidate abstract."], dtype="string"),
            }
        )
        enrichment = pd.DataFrame(
            {
                "doi": pd.Series(["10.1000/blank-enrichment"], dtype="string"),
                "study_title": pd.Series([""], dtype="string"),
                "abstract": pd.Series([""], dtype="string"),
            }
        )

        merged = merged_extraction_metadata(candidate, enrichment)

        self.assertEqual(merged.iloc[0]["study_title"], "Candidate title")
        self.assertEqual(merged.iloc[0]["abstract"], "A usable candidate abstract.")

    def test_nonblank_enrichment_cache_does_not_override_candidate_abstract(self) -> None:
        candidate = pd.DataFrame(
            [{"doi": "10.1000/canonical", "abstract": "Canonical candidate abstract."}]
        )
        enrichment = pd.DataFrame(
            [{"doi": "10.1000/canonical", "abstract": "Stale enrichment-cache abstract."}]
        )

        merged = merged_extraction_metadata(candidate, enrichment)

        self.assertEqual(merged.iloc[0]["abstract"], "Canonical candidate abstract.")

    def test_curated_clear_is_not_refilled_from_enrichment_cache(self) -> None:
        doi = "10.1000/foreign-abstract"
        candidate = pd.DataFrame([{"doi": doi, "study_title": "Provider title", "abstract": ""}])
        enrichment = pd.DataFrame(
            [{"doi": doi, "study_title": "Provider title", "abstract": "Abstract of another publication."}]
        )
        with tempfile.TemporaryDirectory() as tmp:
            overrides = Path(tmp) / "paper_metadata_overrides.json"
            overrides.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "doi": doi.upper(),
                                "fields": {"study_title": "Curated title of the registered work"},
                                "clear_fields": ["abstract"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            merged = merged_extraction_metadata(candidate, enrichment, curated_overrides_path=overrides)
            legacy = merged_extraction_metadata(candidate, enrichment, curated_overrides_path=None)

        self.assertEqual(merged.iloc[0]["abstract"], "")
        self.assertEqual(merged.iloc[0]["study_title"], "Curated title of the registered work")
        self.assertEqual(legacy.iloc[0]["abstract"], "Abstract of another publication.")

    def test_candidate_ledger_supplies_metadata_when_enrichment_row_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_table = root / "candidate.parquet"
            metadata_table = root / "metadata.parquet"
            prescreen_table = root / "prescreen.parquet"
            domain_table = root / "domain.parquet"
            output_table = root / "routes.parquet"
            summary_json = root / "summary.json"
            counts_csv = root / "counts.csv"
            doi = "10.1000/candidate-only-metadata"

            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Candidate-ledger psychedelic trial",
                        "abstract": "A retained trial with metadata already present in the ledger.",
                        "publication_type": "Journal Article",
                    }
                ]
            ).to_parquet(candidate_table, index=False)
            pd.DataFrame(
                [{"doi": "10.1000/different", "study_title": "Different enriched record"}]
            ).to_parquet(metadata_table, index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                    }
                ]
            ).to_parquet(prescreen_table, index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "screening_decision": "include_in_scope",
                        "domain_route": "clinical_outcome",
                        "all_domain_tags": "clinical_outcome",
                        "paper_type_group": "primary",
                        "paper_type": "primary",
                    }
                ]
            ).to_parquet(domain_table, index=False)

            build_extraction_routes(
                metadata_table=metadata_table,
                candidate_table=candidate_table,
                prescreen_table=prescreen_table,
                domain_table=domain_table,
                manual_overrides_path=None,
                manual_fulltext_access_overrides_path=None,
                fulltext_dir=root / "fulltext",
                paper_root=root / "papers",
                output_table=output_table,
                summary_json=summary_json,
                counts_csv=counts_csv,
                update_candidate_table=False,
            )

            routes = pd.read_parquet(output_table)

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes.loc[0, "doi"], doi)
        self.assertEqual(routes.loc[0, "study_title"], "Candidate-ledger psychedelic trial")
        self.assertEqual(routes.loc[0, "domain_route"], "clinical_outcome")

    def test_fulltext_status_rejects_unverified_canonical_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fulltext_dir = Path(tmp) / "fulltext"
            doi = "10.1000/unverified"
            canonical = fulltext_dir / "articles" / f"{doi_to_slug(doi)}.json"
            canonical.parent.mkdir(parents=True)
            canonical.write_text(json.dumps({"best_char_count": 2000}), encoding="utf-8")
            audit = write_gate_table(Path(tmp), [])

            status = fulltext_status_for_doi(
                doi,
                fulltext_dir,
                identity_verdicts=audit,
            )

        self.assertFalse(status["has_converted_full_text"])
        self.assertEqual(status["fulltext_artifact_paths"], "")
        self.assertEqual(status["fulltext_char_count"], 0)

    def test_verified_xml_requires_nonempty_article_body(self) -> None:
        cases = [
            ("europepmc_fulltext_xml", "jats_xml", "<article><front><abstract>Abstract only</abstract></front></article>", False),
            ("europepmc_fulltext_xml", "jats_xml", "<article><body> </body></article>", False),
            ("europepmc_fulltext_xml", "jats_xml", "<article><body><p>Article results</p></body></article>", True),
            ("grobid", "tei_xml", '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><abstract>Catalog abstract</abstract></teiHeader><text><body/></text></TEI>', False),
            ("grobid", "tei_xml", '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div><p>Short original clinical letter results.</p></div></body></text></TEI>', True),
            ("grobid", "tei_xml", "<TEI><text><body>Broken XML", False),
        ]
        for backend, source_format, xml, expected in cases:
            with self.subTest(backend=backend, xml=xml), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                doi = "10.1000/verified-jats"
                canonical = root / "articles" / f"{doi_to_slug(doi)}.json"
                canonical.parent.mkdir()
                canonical.write_text(json.dumps({
                    "best_char_count": 2000,
                    "best_backend": backend,
                    "extractions": [{
                        "backend": backend,
                        "metadata": {"format": source_format},
                        "text": xml,
                    }],
                }))
                audit = write_gate_table(root, [{
                    "requested_doi": doi,
                    "artifact_path": str(canonical.resolve()),
                    "identity_verified": True,
                }])
                status = fulltext_status_for_doi(doi, root, identity_verdicts=audit)
                self.assertEqual(status["has_converted_full_text"], expected)
                self.assertEqual(status["fulltext_char_count"], 2000 if expected else 0)

    def test_primary_paper_uses_general_route_without_domain_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fulltext_dir = Path(tmp) / "fulltext"
            doi = "10.1000/primary"
            artifact = fulltext_dir / "articles" / f"{doi_to_slug(doi)}.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                json.dumps(
                    {
                        "best_char_count": 1200,
                        "source_identity": {"status": "verified_exact_doi"},
                    }
                ),
                encoding="utf-8",
            )
            audit = write_gate_table(
                Path(tmp),
                [
                    {
                        "requested_doi": doi,
                        "artifact_path": str(artifact.resolve()),
                        "identity_verified": True,
                    }
                ],
            )

            metadata_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Psilocybin trial with imaging outcomes",
                        "study_year": "2024",
                        "abstract": "Patients were randomized and brain network outcomes were measured.",
                        "publication_type": "Journal Article | Randomized Controlled Trial",
                        "trial_registry_ids": "NCT1",
                        "best_pdf_url": "https://example.org/paper.pdf",
                        "open_access_status": "gold",
                    }
                ]
            )
            prescreen_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome|safety|bridge_clinical_mechanism",
                    }
                ]
            )
            literature_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "source_family": "primary_or_unclear",
                        "literature_type_confidence": "medium",
                    }
                ]
            )

            rows = build_route_rows(
                metadata_df,
                prescreen_df,
                literature_df,
                fulltext_dir=fulltext_dir,
                generated_at_utc="2026-05-28T00:00:00+00:00",
                identity_verdicts=audit,
            )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_primary"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"primary_general"})
        self.assertTrue(all(row["access_tier"] == "full_text_available" for row in rows))
        self.assertTrue(all(row["has_converted_full_text"] for row in rows))
        self.assertTrue(all(row["bridge_clinical_mechanism"] for row in rows))
        self.assertTrue(all(row["route_action"] == "extract_from_full_text" for row in rows))

    def test_build_extraction_routes_uses_gemini_domain_table_for_paper_type_and_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata_table = root / "metadata.parquet"
            prescreen_table = root / "prescreen.parquet"
            domain_table = root / "domain.parquet"
            output_table = root / "routes.parquet"
            summary_json = root / "summary.json"
            counts_csv = root / "counts.csv"

            doi = "10.1000/gemini-route"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Psilocybin trial outcomes",
                        "study_year": "2024",
                        "abstract": "A randomized trial reports depression outcomes.",
                        "publication_type": "Journal Article",
                    }
                ]
            ).to_parquet(metadata_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome",
                    }
                ]
            ).to_parquet(prescreen_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "screening_decision": "include_in_scope",
                        "domain_route": "clinical_outcome",
                        "domain_tags": "clinical_outcome",
                        "paper_type_group": "primary",
                        "paper_type": "primary",
                        "paper_type_reason": "Reports original empirical outcomes.",
                        "domain_route_confidence": "high",
                    }
                ]
            ).to_parquet(domain_table, engine="pyarrow", index=False)

            build_extraction_routes(
                metadata_table=metadata_table,
                candidate_table=root / "candidate_papers.parquet",
                prescreen_table=prescreen_table,
                domain_table=domain_table,
                manual_overrides_path=None,
                manual_fulltext_access_overrides_path=None,
                fulltext_dir=root / "fulltext",
                paper_root=root / "papers",
                output_table=output_table,
                summary_json=summary_json,
                counts_csv=counts_csv,
                update_candidate_table=False,
            )

            routes = pd.read_parquet(output_table)

        self.assertEqual(routes.loc[0, "source_family"], "primary")
        self.assertEqual(routes.loc[0, "source_type"], "primary")
        self.assertEqual(routes.loc[0, "domain_route"], "clinical_outcome")
        self.assertEqual(routes.loc[0, "prompt_profile"], "primary_clinical")

    def test_dissertation_metadata_overrides_model_primary_classification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata_table = root / "metadata.parquet"
            prescreen_table = root / "prescreen.parquet"
            domain_table = root / "domain.parquet"
            output_table = root / "routes.parquet"
            summary_json = root / "summary.json"
            counts_csv = root / "counts.csv"

            doi = "10.1000/model-called-primary-thesis"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Ketamine thesis",
                        "study_year": "2024",
                        "abstract": "This thesis reports original mixed-methods ketamine research.",
                        "publication_type": "dissertation",
                    }
                ]
            ).to_parquet(metadata_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome|intervention_context",
                    }
                ]
            ).to_parquet(prescreen_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "screening_decision": "include_in_scope",
                        "domain_route": "clinical_outcome",
                        "all_domain_tags": "clinical_outcome|intervention_context",
                        "paper_type_group": "primary",
                        "paper_type": "primary",
                        "paper_type_reason": "Model says this thesis reports original empirical outcomes.",
                    }
                ]
            ).to_parquet(domain_table, engine="pyarrow", index=False)

            build_extraction_routes(
                metadata_table=metadata_table,
                candidate_table=root / "candidate_papers.parquet",
                prescreen_table=prescreen_table,
                domain_table=domain_table,
                manual_overrides_path=None,
                manual_fulltext_access_overrides_path=None,
                fulltext_dir=root / "fulltext",
                paper_root=root / "papers",
                output_table=output_table,
                summary_json=summary_json,
                counts_csv=counts_csv,
                update_candidate_table=False,
            )

            routes = pd.read_parquet(output_table)

        self.assertEqual(len(routes), 1)
        self.assertFalse(bool(routes.loc[0, "retained_for_extraction_candidate"]))
        self.assertEqual(routes.loc[0, "source_family"], "non_primary_publication")
        self.assertEqual(routes.loc[0, "source_type"], "non_primary_publication")
        self.assertEqual(
            routes.loc[0, "non_primary_flags"],
            "thesis_or_dissertation_publication_type|thesis_or_dissertation_title|thesis_or_dissertation_doi|thesis_or_dissertation_abstract",
        )
        self.assertEqual(routes.loc[0, "domain_route"], "context_only")
        self.assertEqual(routes.loc[0, "route_action"], "skip_or_context_only")
        self.assertEqual(routes.loc[0, "prompt_profile"], "context_only_or_skip")

    def test_abstract_only_thesis_mention_does_not_override_journal_article(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata_table = root / "metadata.parquet"
            prescreen_table = root / "prescreen.parquet"
            domain_table = root / "domain.parquet"
            output_table = root / "routes.parquet"
            summary_json = root / "summary.json"
            counts_csv = root / "counts.csv"

            doi = "10.1000/abstract-only-thesis-mention"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Psilocybin clinical outcomes",
                        "study_year": "2024",
                        "abstract": "The background cites a doctoral thesis, but this paper reports a trial.",
                        "publication_type": "Journal Article",
                        "study_journal": "Example Medical Journal",
                    }
                ]
            ).to_parquet(metadata_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome",
                    }
                ]
            ).to_parquet(prescreen_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "screening_decision": "include_in_scope",
                        "domain_route": "clinical_outcome",
                        "all_domain_tags": "clinical_outcome",
                        "paper_type_group": "primary",
                        "paper_type": "primary",
                        "paper_type_reason": "Reports original empirical outcomes.",
                    }
                ]
            ).to_parquet(domain_table, engine="pyarrow", index=False)

            build_extraction_routes(
                metadata_table=metadata_table,
                candidate_table=root / "candidate_papers.parquet",
                prescreen_table=prescreen_table,
                domain_table=domain_table,
                manual_overrides_path=None,
                manual_fulltext_access_overrides_path=None,
                fulltext_dir=root / "fulltext",
                paper_root=root / "papers",
                output_table=output_table,
                summary_json=summary_json,
                counts_csv=counts_csv,
                update_candidate_table=False,
            )

            routes = pd.read_parquet(output_table)

        self.assertEqual(thesis_or_dissertation_flags(routes.loc[0].to_dict()), "")
        self.assertTrue(bool(routes.loc[0, "retained_for_extraction_candidate"]))
        self.assertEqual(routes.loc[0, "source_family"], "primary")
        self.assertEqual(routes.loc[0, "domain_route"], "clinical_outcome")
        self.assertEqual(routes.loc[0, "route_action"], "extract_from_abstract_only")

    def test_secondary_meta_analysis_uses_general_review_profile_without_domain_table(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "study_title": "A meta-analysis of MDMA treatment",
                    "study_year": "2022",
                    "abstract": "This meta-analysis reviewed randomized trials.",
                    "publication_type": "Journal Article | Meta-Analysis",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "retained_for_extraction_candidate": True,
                    "source_family": "secondary_literature",
                    "primary_secondary_source_type": "meta_analysis",
                    "secondary_source_types": "meta_analysis|review",
                    "literature_type_confidence": "high",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_topic_coverage"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"secondary_meta_analysis"})
        self.assertEqual({row["schema_profile"] for row in rows}, {"meta_analysis_evidence_schema"})
        self.assertEqual({row["access_tier"] for row in rows}, {"abstract_only"})
        self.assertEqual({row["route_confidence"] for row in rows}, {"low"})
        self.assertIn("report-type driven", rows[0]["route_basis"])

    def test_secondary_literature_ignores_model_topic_routes(self) -> None:
        doi = "10.1000/secondary-topic-collapse"
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "study_title": "Systematic review of psychedelic outcomes",
                    "abstract": "A systematic review covering clinical and safety outcomes.",
                    "publication_type": "Systematic Review",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "retained_for_extraction_candidate": True,
                    "source_family": "secondary_literature",
                    "primary_secondary_source_type": "systematic_review",
                    "secondary_source_types": "systematic_review|review",
                    "literature_type_confidence": "high",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "domain_route": route,
                    "all_domain_tags": "clinical_outcome|safety_tolerability",
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "In-scope secondary literature.",
                    "methodological_validity_tags": "evidence_quality_bias",
                    "model": "gpt-6-luna",
                }
                for route in ("clinical_outcome", "safety_tolerability")
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-07-17T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "general_topic_coverage")
        self.assertEqual(rows[0]["domain_tags"], "")
        self.assertEqual(rows[0]["domain_routing_primary_domain"], "")
        self.assertEqual(rows[0]["prompt_profile"], "secondary_structured_review")
        self.assertEqual(rows[0]["schema_profile"], "review_coverage_schema")
        self.assertEqual(rows[0]["methodological_validity_tags"], "evidence_quality_bias")
        self.assertIn("report-type driven", rows[0]["route_basis"])

    def test_manual_fulltext_access_override_suppresses_pdf_download_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/not-oa",
                    "study_title": "Closed article with misleading PDF URL",
                    "study_year": "2024",
                    "abstract": "This retained article has enough abstract text for fallback extraction.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://example.org/article.pdf",
                    "pdf_url_candidates": "https://example.org/article.pdf",
                    "open_access_status": "green",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/not-oa",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/not-oa",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-06-20T00:00:00+00:00",
            manual_fulltext_access_overrides={
                "10.1000/not-oa": {
                    "manual_access_action": "suppress_pdf_download",
                    "open_access_status": "closed",
                    "open_access_is_oa": False,
                    "manual_reason": "Manual review: no open PDF access.",
                }
            },
        )

        self.assertEqual({row["access_tier"] for row in rows}, {"abstract_only"})
        self.assertEqual({row["route_action"] for row in rows}, {"extract_from_abstract_only"})
        self.assertEqual({row["open_access_status"] for row in rows}, {"closed"})
        self.assertEqual({row["best_pdf_url"] for row in rows}, {""})
        self.assertEqual({row["manual_fulltext_access_action"] for row in rows}, {"suppress_pdf_download"})
        self.assertEqual({row["source_text_state"] for row in rows}, {"public_abstract_only"})
        self.assertEqual({row["source_identity_verified"] for row in rows}, {False})

    def test_abstract_only_override_wins_over_a_valid_local_pdf(self) -> None:
        doi = "10.1000/non-english"
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "study_title": "A valid non-English full-text article",
                    "study_year": "2024",
                    "abstract": "An English abstract remains available for extraction.",
                    "publication_type": "Journal Article",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            paper_root = Path(tmp) / "papers"
            paper_root.mkdir(parents=True)
            (paper_root / f"{doi_to_slug(doi)}__reviewed.pdf").write_bytes(b"%PDF-1.4\n")
            rows = build_route_rows(
                metadata_df,
                prescreen_df,
                literature_df,
                fulltext_dir=Path(tmp) / "fulltext",
                generated_at_utc="2026-07-10T00:00:00+00:00",
                paper_root=paper_root,
                manual_fulltext_access_overrides={
                    doi: {
                        "manual_access_action": "abstract_only",
                        "manual_reason": "Full text retained, but current extraction uses the English abstract.",
                    }
                },
            )

        self.assertEqual({row["access_tier"] for row in rows}, {"abstract_only"})
        self.assertEqual({row["route_action"] for row in rows}, {"extract_from_abstract_only"})
        self.assertEqual({row["source_text_state"] for row in rows}, {"public_abstract_only"})
        self.assertEqual(
            {row["source_text_state_reason"] for row in rows},
            {"Full text retained, but current extraction uses the English abstract."},
        )

    def test_prescreen_excluded_preprint_does_not_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "study_title": "Speech markers of psychedelic-induced psychological change",
                    "study_year": "2025",
                    "abstract": "A preprint abstract.",
                    "publication_type": "posted-content",
                    "study_journal": "bioRxiv",
                    "publisher": "openRxiv",
                    "best_pdf_url": "https://www.biorxiv.org/content/10.1101/2025.04.16.649217.full.pdf",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_preprint_or_unpublished",
                    "routing_tags": "",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows, [])

    def test_non_evidence_artifact_blocks_stale_model_route_rows(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "study_title": "Table 2_Dose-dependent changes in brain activity following psilocybin.xlsx",
                    "study_year": "2025",
                    "abstract": "Dose-dependent brain activity and functional connectivity are reported.",
                    "publication_type": "dataset",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_non_evidence_artifact",
                    "routing_tags": "",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "brain_system",
                    "domain_tag": "brain_system",
                    "screening_decision": "include_in_scope",
                    "paper_type_group": "primary",
                    "paper_type": "primary",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df=domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows, [])

    def test_candidate_status_updates_summarize_routes_and_prescreen_exclusions(self) -> None:
        generated_at = "2026-05-28T00:00:00+00:00"
        candidate_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/article",
                    "publication_type": "Journal Article",
                    "study_title": "Published trial",
                    "abstract": "A trial abstract.",
                },
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "publication_type": "posted-content",
                    "study_journal": "bioRxiv",
                    "study_title": "Preprint",
                    "abstract": "A preprint abstract.",
                },
                {
                    "doi": "10.1000/thesis",
                    "publication_type": "dissertation",
                    "study_title": "Ketamine thesis",
                    "abstract": "This thesis is concerned with ketamine.",
                },
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/article",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                },
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_preprint_or_unpublished",
                    "prescreen_reason": "Record appears to be a preprint.",
                    "routing_tags": "",
                },
                {
                    "doi": "10.1000/thesis",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                },
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/article",
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "high",
                },
                {
                    "doi": "10.1000/thesis",
                    "source_family": "non_primary_publication",
                    "non_primary_flags": "thesis_or_dissertation_publication_type|thesis_or_dissertation_abstract",
                    "literature_type_confidence": "high",
                }
            ]
        )
        route_rows = [
            {
                "doi": "10.1000/article",
                "retained_for_extraction_candidate": True,
                "route_action": "extract_from_full_text",
                "access_tier": "full_text_available",
                "domain_route": "clinical_outcome",
                "domain_screening_decision": "include_in_scope",
                "prompt_profile": "primary_clinical",
                "schema_profile": "primary_evidence_schema",
                "has_converted_full_text": True,
                "fulltext_artifact_paths": "/tmp/article.json",
                "fulltext_char_count": 1234,
            },
            {
                "doi": "10.1000/thesis",
                "retained_for_extraction_candidate": False,
                "route_action": "skip_or_context_only",
                "access_tier": "full_text_available",
                "domain_route": "context_only",
                "prompt_profile": "context_only_or_skip",
                "schema_profile": "context_only_schema",
            }
        ]
        updates = build_candidate_status_updates(
            candidate_df=candidate_df,
            prescreen_df=prescreen_df,
            literature_df=literature_df,
            route_rows=route_rows,
            generated_at_utc=generated_at,
        )
        by_doi = {row["doi"]: row for row in updates.to_dict("records")}

        article = by_doi["10.1000/article"]
        self.assertEqual(article["publication_stage"], "published")
        self.assertTrue(article["retained_for_extraction_candidate"])
        self.assertEqual(article["extraction_route_status"], "ready_for_article_text_extraction")
        self.assertEqual(article["extraction_domain_routes"], "clinical_outcome")
        self.assertEqual(article["best_extraction_access_tier"], "full_text_available")
        self.assertTrue(article["has_converted_full_text"])
        self.assertEqual(article["source_text_state"], "public_full_text_verified")
        self.assertTrue(article["source_identity_verified"])

        preprint = by_doi["10.1101/2025.04.16.649217"]
        self.assertEqual(preprint["publication_stage"], "preprint")
        self.assertFalse(preprint["retained_for_extraction_candidate"])
        self.assertFalse(preprint["prescreen_retained_for_extraction_candidate"])
        self.assertEqual(preprint["prescreen_actions"], "exclude_preprint_or_unpublished")
        self.assertEqual(preprint["extraction_route_status"], "not_retained_for_extraction")
        self.assertEqual(preprint["source_text_state"], "excluded_from_extraction")

        thesis = by_doi["10.1000/thesis"]
        self.assertFalse(thesis["retained_for_extraction_candidate"])
        self.assertEqual(thesis["literature_source_family"], "non_primary_publication")
        self.assertEqual(
            thesis["non_primary_flags"],
            "thesis_or_dissertation_publication_type|thesis_or_dissertation_abstract",
        )
        self.assertEqual(thesis["extraction_route_status"], "context_only_or_skip")

    def test_published_article_with_preprint_pdf_url_is_not_held_out(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1021/acschemneuro.2c00123",
                    "study_title": "Acute behavioral and neurochemical effects in adult zebrafish",
                    "study_year": "2022",
                    "abstract": "A journal article abstract.",
                    "publication_type": "Journal Article | Research Support, Non-U.S. Gov't",
                    "study_journal": "ACS Chemical Neuroscience",
                    "publisher": "American Chemical Society (ACS)",
                    "best_pdf_url": "https://www.biorxiv.org/content/10.1101/2022.01.19.476767.full.pdf",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1021/acschemneuro.2c00123",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1021/acschemneuro.2c00123",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["route_action"], "extract_from_abstract_only")

    def test_valid_local_pdf_gets_local_pdf_route_before_pdf_url_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_root = root / "papers"
            pdf_path = paper_root / "archive" / "excluded" / "10.1000_local_pdf__abc123.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.7\nvalid enough for the route audit")
            metadata_df = pd.DataFrame(
                [
                    {
                        "doi": "10.1000/local-pdf",
                        "study_title": "Psilocybin trial with a local PDF",
                        "abstract": "A clinical trial abstract.",
                        "publication_type": "Journal Article",
                        "best_pdf_url": "https://example.org/paper.pdf",
                    }
                ]
            )
            prescreen_df = pd.DataFrame(
                [
                    {
                        "doi": "10.1000/local-pdf",
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome",
                    }
                ]
            )
            literature_df = pd.DataFrame(
                [
                    {
                        "doi": "10.1000/local-pdf",
                        "retained_for_extraction_candidate": True,
                        "source_family": "primary_or_unclear",
                        "literature_type_confidence": "medium",
                    }
                ]
            )

            rows = build_route_rows(
                metadata_df,
                prescreen_df,
                literature_df,
                fulltext_dir=root / "missing-fulltext",
                paper_root=paper_root,
                generated_at_utc="2026-05-28T00:00:00+00:00",
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["access_tier"], "local_pdf_available")
        self.assertEqual(rows[0]["route_action"], "convert_local_pdf_then_extract")
        self.assertTrue(rows[0]["has_local_pdf"])
        self.assertIn("10.1000_local_pdf__abc123.pdf", rows[0]["local_pdf_paths"])
        self.assertTrue(rows[0]["has_pdf_url"])
        self.assertTrue(rows[0]["has_probable_pdf_url"])
        self.assertEqual(rows[0]["pdf_url_quality"], "probable_pdf")
        self.assertFalse(rows[0]["has_converted_full_text"])

    def rejected_fulltext_route(self, *, abstract: str) -> dict:
        doi = "10.1000/rejected-fulltext"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_root = root / "papers"
            pdf_path = paper_root / "10.1000_rejected_fulltext__abc123.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.7\nthe PDF that was converted and rejected")
            fulltext_dir = root / "fulltext"
            artifact = fulltext_dir / "articles" / f"{doi_to_slug(doi)}.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(json.dumps({"best_char_count": 5000}), encoding="utf-8")
            audit = write_gate_table(
                root,
                [{"requested_doi": doi, "artifact_path": str(artifact.resolve()), "identity_verified": False}],
            )
            rows = build_route_rows(
                pd.DataFrame([{"doi": doi, "study_title": "Psilocybin trial", "abstract": abstract,
                               "publication_type": "Journal Article"}]),
                pd.DataFrame([{"doi": doi, "prescreen_decision": "retain", "retained_for_extraction_candidate": True,
                               "prescreen_action": "retain_for_extraction_candidate",
                               "routing_tags": "clinical_outcome"}]),
                pd.DataFrame([{"doi": doi, "retained_for_extraction_candidate": True,
                               "source_family": "primary_or_unclear", "literature_type_confidence": "medium"}]),
                fulltext_dir=fulltext_dir,
                paper_root=paper_root,
                identity_verdicts=audit,
                generated_at_utc="2026-11-01T00:00:00+00:00",
            )
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_rejected_full_text_falls_back_to_abstract_instead_of_reconversion(self) -> None:
        row = self.rejected_fulltext_route(abstract="A clinical trial abstract.")

        self.assertEqual(row["access_tier"], "abstract_only")
        self.assertEqual(row["route_action"], "extract_from_abstract_only")
        self.assertEqual(row["fulltext_identity_status"], "identity_unverified")
        self.assertFalse(row["has_converted_full_text"])
        self.assertTrue(row["has_local_pdf"])
        self.assertIn("does not allow the artifact", row["source_text_state_reason"])
        self.assertFalse(row["source_identity_verified"])

    def test_rejected_full_text_without_abstract_waits_for_text(self) -> None:
        row = self.rejected_fulltext_route(abstract="")

        self.assertEqual(row["access_tier"], "no_usable_text")
        self.assertEqual(row["route_action"], "hold_until_text_available")

    def test_probable_pdf_url_does_not_block_available_abstract(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf",
                    "study_title": "Psilocybin study with probable PDF URL",
                    "abstract": "A study abstract.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://publisher.example/content/pdf/10.1000/probable.pdf",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["access_tier"], "abstract_only")
        self.assertEqual(rows[0]["route_action"], "extract_from_abstract_only")
        self.assertTrue(rows[0]["has_pdf_url"])
        self.assertTrue(rows[0]["has_probable_pdf_url"])
        self.assertEqual(rows[0]["pdf_url_quality"], "probable_pdf")
        self.assertIn("content/pdf", rows[0]["probable_pdf_url_candidates"])

    def test_probable_pdf_url_without_abstract_routes_to_download(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf-no-abstract",
                    "study_title": "Psilocybin study without an abstract",
                    "abstract": "",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://publisher.example/content/pdf/10.1000/probable.pdf",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf-no-abstract",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf-no-abstract",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["access_tier"], "pdf_download_url_available")
        self.assertEqual(rows[0]["route_action"], "download_pdf_then_extract")

    def test_terminal_pdf_failure_falls_back_to_abstract_route(self) -> None:
        doi = "10.1000/terminal-pdf-failure"
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "study_title": "Psilocybin study with a mismatched PDF",
                    "abstract": "A usable study abstract remains available for extraction.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://publisher.example/content/pdf/wrong-paper.pdf",
                    "pdf_download_status": "download_failed",
                    "pdf_download_failure_category": "source_identity_mismatch",
                    "pdf_download_failure_categories": "source_identity_mismatch",
                    "pdf_download_retry_recommended": True,
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-07-21T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["access_tier"], "abstract_only")
        self.assertEqual(rows[0]["route_action"], "extract_from_abstract_only")
        self.assertTrue(rows[0]["pdf_download_terminal_failure"])
        self.assertFalse(rows[0]["pdf_download_retry_recommended"])
        self.assertFalse(rows[0]["has_pdf_url"])

    def test_weak_pdf_url_stays_visible_but_does_not_route_to_automated_download(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/landing-url",
                    "study_title": "Psilocybin study with landing page URL",
                    "abstract": "A study abstract.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://doi.org/10.1000/landing-url",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/landing-url",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/landing-url",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["access_tier"], "abstract_only")
        self.assertEqual(rows[0]["route_action"], "extract_from_abstract_only")
        self.assertTrue(rows[0]["has_pdf_url"])
        self.assertFalse(rows[0]["has_probable_pdf_url"])
        self.assertEqual(rows[0]["pdf_url_quality"], "possible_landing_page")
        self.assertEqual(rows[0]["probable_pdf_url_candidates"], "")
        self.assertEqual(rows[0]["other_url_candidates"], "https://doi.org/10.1000/landing-url")

    def test_primary_gap_domain_tags_do_not_create_specific_routes_without_domain_table(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "study_title": "Psilocybin session and exposure study",
                    "abstract": "The study measured plasma concentration, mystical experience, and preparation.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "subjective_experience|pharmacokinetics_exposure|intervention_context|real_world_use_public_health",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_primary"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"primary_general"})
        self.assertEqual(rows[0]["domain_tags"], "")
        self.assertIn("no model-assigned domain table supplied", rows[0]["route_basis"])

    def test_domain_routing_table_overrides_prescreen_tag_fallback(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "study_title": "Psilocybin and brain network connectivity",
                    "abstract": "Brain network outcomes were measured.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|brain_system",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "brain_system",
                    "domain_tag": "brain_system",
                    "all_domain_tags": "clinical_outcome|brain_system",
                    "primary_domain": "brain_system",
                    "screening_decision": "include_for_extraction",
                    "screening_reason": "In-scope brain-system evidence.",
                    "methodological_validity_tags": "blinding_expectancy_validity",
                    "domain_route_confidence": "medium",
                    "domain_route_basis": "domain tag:brain_system",
                    "needs_human_review": True,
                    "model": "gpt-6-luna",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "brain_system")
        self.assertEqual(rows[0]["prompt_profile"], "primary_brain_system")
        self.assertEqual(rows[0]["domain_routing_primary_domain"], "brain_system")
        self.assertEqual(rows[0]["domain_screening_decision"], "include_for_extraction")
        self.assertEqual(rows[0]["domain_screening_reason"], "In-scope brain-system evidence.")
        self.assertEqual(rows[0]["methodological_validity_tags"], "blinding_expectancy_validity")
        self.assertEqual(rows[0]["domain_routing_model"], "gpt-6-luna")
        self.assertTrue(rows[0]["domain_needs_human_review"])
        self.assertIn("domain_route_basis:domain tag:brain_system", rows[0]["route_basis"])

    def test_methodological_validity_tags_do_not_replace_domain_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "study_title": "Blinding in psychedelic trials",
                    "abstract": "The study evaluates expectancy and blinding validity.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "clinical_outcome",
                    "domain_tag": "clinical_outcome",
                    "all_domain_tags": "clinical_outcome",
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_for_extraction",
                    "methodological_validity_tags": "blinding_expectancy_validity",
                    "domain_route_confidence": "high",
                    "domain_route_basis": "domain tag:clinical_outcome",
                    "needs_human_review": False,
                    "model": "gpt-6-luna",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "clinical_outcome")
        self.assertEqual(rows[0]["prompt_profile"], "primary_clinical")
        self.assertEqual(rows[0]["methodological_validity_tags"], "blinding_expectancy_validity")
        self.assertEqual(rows[0]["schema_profile"], "primary_evidence_schema")

    def test_model_excluded_record_does_not_create_extraction_task(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "study_title": "Non-psychedelic depression paper",
                    "abstract": "This paper studies a non-psychedelic treatment.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": False,
                    "domain_route": "general_topic",
                    "domain_tag": "",
                    "all_domain_tags": "",
                    "primary_domain": "general_topic",
                    "screening_decision": "exclude_out_of_scope",
                    "screening_reason": "No in-scope psychedelic evidence.",
                    "methodological_validity_tags": "",
                    "domain_route_confidence": "high",
                    "domain_route_basis": "Gemini title/abstract domain routing: out of scope",
                    "needs_human_review": False,
                    "model": "gpt-6-luna",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "screening_excluded")
        self.assertEqual(rows[0]["route_action"], "exclude_after_model_screen")
        self.assertEqual(rows[0]["prompt_profile"], "no_extraction")
        self.assertEqual(rows[0]["schema_profile"], "no_extraction_schema")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])
        self.assertEqual(rows[0]["domain_screening_decision"], "exclude_out_of_scope")

    def test_curated_screening_exclusion_overrides_an_in_scope_model_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "study_title": "Broad treatment guideline",
                    "abstract": "A broad guideline that mentions ketamine only as background.",
                    "publication_type": "Journal Article",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                }
            ]
        )
        reason = "No specific psychedelic, ketamine, or entactogen recommendation."

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            domain_df=domain_df,
            screening_overrides={
                "10.1000/out": {"decision": "exclude_out_of_scope", "reason": reason}
            },
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-07-14T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])
        self.assertEqual(rows[0]["domain_route"], "screening_excluded")
        self.assertEqual(rows[0]["domain_screening_decision"], "exclude_out_of_scope")
        self.assertEqual(rows[0]["domain_screening_reason"], reason)

    def test_non_primary_publication_collapses_to_context_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "study_title": "Editorial on psychedelic therapy",
                    "abstract": "This editorial discusses the field.",
                    "publication_type": "Editorial",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|safety|molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "retained_for_extraction_candidate": True,
                    "source_family": "non_primary_publication",
                    "non_primary_flags": "non_primary_publication_type",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "context_only")
        self.assertEqual(rows[0]["prompt_profile"], "context_only_or_skip")
        self.assertEqual(rows[0]["schema_profile"], "context_only_schema")
        self.assertEqual(rows[0]["route_action"], "skip_or_context_only")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])

    def test_manual_context_only_override_collapses_to_non_extraction_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "study_title": "Bibliometric analysis of psychedelic clinical studies",
                    "abstract": "This article maps the literature.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "domain_route": "general_topic",
                    "all_domain_tags": "clinical_outcome",
                    "primary_domain": "general_topic",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "General topic.",
                    "model": "gpt-6-luna",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-30T00:00:00+00:00",
            manual_overrides={
                "10.1000/bibliometric": {
                    "manual_action": "context_only",
                    "manual_reason": "Manual review: field-mapping paper.",
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "context_only")
        self.assertEqual(rows[0]["prompt_profile"], "context_only_or_skip")
        self.assertEqual(rows[0]["route_action"], "skip_or_context_only")
        self.assertEqual(rows[0]["domain_screening_decision"], "manual_context_only")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])

    def test_manual_domain_override_replaces_general_topic_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "study_title": "Ibogaine: a comprehensive literature review",
                    "abstract": "This review covers anti-addiction evidence.",
                    "publication_type": "Review",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "retained_for_extraction_candidate": True,
                    "source_family": "secondary_literature",
                    "primary_secondary_source_type": "literature_review",
                    "secondary_source_types": "literature_review|review",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "domain_route": "general_topic",
                    "all_domain_tags": "clinical_outcome",
                    "primary_domain": "general_topic",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "General topic.",
                    "model": "gpt-6-luna",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-30T00:00:00+00:00",
            manual_overrides={
                "10.1000/ibogaine-review": {
                    "manual_action": "route_domains",
                    "manual_domain_routes": "clinical_outcome|safety_tolerability",
                    "manual_reason": "Manual review: ibogaine clinical review.",
                }
            },
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_topic_coverage"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"secondary_narrative_review"})
        self.assertEqual({row["domain_screening_decision"] for row in rows}, {"include_in_scope"})
        self.assertTrue(all(row["retained_for_extraction_candidate"] for row in rows))

    def test_manual_source_type_override_reclassifies_qualitative_meta_review(self) -> None:
        doi = "10.1000/qualitative-review"
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "study_title": "Integrating meta-analyses qualitatively",
                    "abstract": "A systematic review integrated prior meta-analyses qualitatively.",
                    "publication_type": "Systematic Review | Meta-Analysis",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "domain_route": "clinical_outcome",
                    "all_domain_tags": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                    "paper_type_group": "secondary_literature",
                    "paper_type": "meta_analysis",
                    "primary_secondary_source_type": "meta_analysis",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            domain_df=domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-07-13T00:00:00+00:00",
            manual_overrides={
                doi: {
                    "manual_source_family": "secondary_literature",
                    "manual_source_type": "systematic_review",
                    "manual_primary_secondary_source_type": "systematic_review",
                    "manual_literature_type_confidence": "high",
                    "manual_paper_type_reason": "The paper integrates prior meta-analyses qualitatively.",
                }
            },
        )

        self.assertEqual({row["source_family"] for row in rows}, {"secondary_literature"})
        self.assertEqual({row["source_type"] for row in rows}, {"systematic_review"})
        self.assertEqual(
            {row["primary_secondary_source_type"] for row in rows}, {"systematic_review"}
        )
        self.assertEqual({row["prompt_profile"] for row in rows}, {"secondary_structured_review"})

    def test_prescreen_context_ignores_excluded_rows(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/a",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "routing_tags": "clinical_outcome",
                },
                {
                    "doi": "10.1000/a",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "routing_tags": "molecular_target",
                },
            ]
        )

        context = prescreen_context_by_doi(df)

        self.assertEqual(context["10.1000/a"]["routing_tags"], ["molecular_target"])


if __name__ == "__main__":
    unittest.main()


def test_converted_pdf_without_an_article_body_routes_to_the_abstract(tmp_path):
    import os

    from pipeline.extract.build_extraction_routes import access_tier

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 meeting abstract")
    text = tmp_path / "paper.json"
    text.write_text(json.dumps({"pdf_local_path": str(pdf)}))
    os.utime(pdf, (1_000, 1_000))
    os.utime(text, (2_000, 2_000))
    status = {"has_converted_full_text": False, "fulltext_identity_status": "", "fulltext_without_article_body": str(text)}
    local = {"has_local_pdf": True, "local_pdf_paths": str(pdf)}

    assert access_tier({"abstract": "An abstract."}, status, local) == "abstract_only"
    assert access_tier({}, status, local) == "no_usable_text"
    os.utime(pdf, (3_000, 3_000))
    assert access_tier({"abstract": "An abstract."}, status, local) == "local_pdf_available"
