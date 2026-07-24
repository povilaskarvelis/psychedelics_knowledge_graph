from __future__ import annotations

import unittest

from pipeline.ingest.open_science_features import (
    FEATURE_OPEN_DATA,
    FEATURE_PREREGISTERED,
    FEATURE_REGISTERED_TRIAL,
    FEATURE_SHARED_CODE,
    local_assertions_and_resource_candidates,
    prospective_registration,
)
from pipeline.ingest.enrich_paper_open_science import (
    apply_publication_semantic_guards,
)


RUN_ID = "test_run"
RETRIEVED_AT = "2026-07-23T00:00:00+00:00"
DOI = "10.1234/focal-paper"


def extract(text: str, *, title: str = "", abstract: str = ""):
    assertions, candidates = local_assertions_and_resource_candidates(
        doi=DOI,
        title=title,
        abstract=abstract,
        publication_type="Journal Article",
        fulltext=text,
        fulltext_path="/tmp/test.xml",
        retrieval_run_id=RUN_ID,
        retrieved_at_utc=RETRIEVED_AT,
    )
    return assertions, candidates


def features(text: str, *, title: str = "", abstract: str = "") -> set[str]:
    assertions, _ = extract(text, title=title, abstract=abstract)
    return {row["feature"] for row in assertions}


class OpenScienceFeatureTests(unittest.TestCase):
    def test_explicit_focal_trial_registration(self) -> None:
        observed = features(
            "<head>Trial registration</head>"
            "This trial was registered at ClinicalTrials.gov (NCT01234567)."
        )
        self.assertIn(FEATURE_REGISTERED_TRIAL, observed)
        self.assertNotIn(FEATURE_PREREGISTERED, observed)

    def test_other_ongoing_trial_mention_is_not_focal_registration(self) -> None:
        observed = features(
            "An ongoing trial registered at ClinicalTrials.gov (NCT01234567) "
            "is testing a related intervention."
        )
        self.assertNotIn(FEATURE_REGISTERED_TRIAL, observed)

    def test_explicit_prospective_trial_registration_is_preregistered(self) -> None:
        observed = features(
            "Our trial was prospectively registered (ClinicalTrials.gov "
            "NCT01234567) before participant enrollment."
        )
        self.assertEqual(
            observed,
            {FEATURE_REGISTERED_TRIAL, FEATURE_PREREGISTERED},
        )

    def test_retrospective_registration_is_not_preregistered(self) -> None:
        observed = features(
            "The trial was retrospectively registered with ClinicalTrials.gov "
            "(NCT01234567)."
        )
        self.assertIn(FEATURE_REGISTERED_TRIAL, observed)
        self.assertNotIn(FEATURE_PREREGISTERED, observed)

    def test_open_repository_data_statement(self) -> None:
        observed = features(
            "<head>Data availability</head>"
            "The raw data generated in this study are publicly available in "
            "Dryad at https://doi.org/10.5061/dryad.abc123."
        )
        self.assertIn(FEATURE_OPEN_DATA, observed)

    def test_data_available_on_request_is_not_open_data(self) -> None:
        observed = features(
            "<head>Data availability</head>"
            "Data are available from the authors upon reasonable request. "
            "A project page is at https://osf.io/abc12/."
        )
        self.assertNotIn(FEATURE_OPEN_DATA, observed)

    def test_future_data_release_is_not_open_data(self) -> None:
        observed = features(
            "<head>Data availability</head>"
            "The data will be made available at "
            "https://doi.org/10.5281/zenodo.1234567 after publication."
        )
        self.assertNotIn(FEATURE_OPEN_DATA, observed)

    def test_future_data_added_later_is_not_open_data(self) -> None:
        observed = features(
            "<head>Data availability</head>"
            "Materials are available at https://osf.io/abc12/. "
            "The data will then be added to that repository."
        )
        self.assertNotIn(FEATURE_OPEN_DATA, observed)

    def test_external_openneuro_data_use_is_not_sharing(self) -> None:
        observed = features(
            "We downloaded a previously published dataset from "
            "https://openneuro.org/datasets/ds000001 and reanalyzed it."
        )
        self.assertNotIn(FEATURE_OPEN_DATA, observed)

    def test_study_specific_github_code_is_shared_code(self) -> None:
        observed = features(
            "<head>Code availability</head>"
            "Our custom analysis code used to generate the results is "
            "available at https://github.com/example/focal-analysis."
        )
        self.assertIn(FEATURE_SHARED_CODE, observed)

    def test_code_and_raw_data_at_figshare_counts_as_both(self) -> None:
        observed = features(
            "Med-PC code for the task as well as the raw data are available "
            "at https://doi.org/10.6084/m9.figshare.14933127."
        )
        self.assertIn(FEATURE_OPEN_DATA, observed)
        self.assertIn(FEATURE_SHARED_CODE, observed)

    def test_custom_script_linked_in_dryad_counts_as_code_and_data(self) -> None:
        observed = features(
            "Raw data were processed and combined using a custom MATLAB "
            "script (https://doi.org/10.5061/dryad.abc123)."
        )
        self.assertIn(FEATURE_OPEN_DATA, observed)
        self.assertIn(FEATURE_SHARED_CODE, observed)

    def test_code_for_reproducing_analyses_is_shared_code(self) -> None:
        observed = features(
            "<head>Data availability</head>"
            "Codes for reproducing the datasets and analyses can be accessed "
            "at https://github.com/example/focal-analysis."
        )
        self.assertIn(FEATURE_SHARED_CODE, observed)

    def test_generic_software_repository_is_not_shared_code(self) -> None:
        observed = features(
            "Analysis used the third-party software library available at "
            "https://github.com/scipy/scipy version 1.11."
        )
        self.assertNotIn(FEATURE_SHARED_CODE, observed)

    def test_generic_software_in_code_availability_is_not_shared_code(self) -> None:
        observed = features(
            "<head>Code availability</head>"
            "Analysis was performed with code available from the third-party "
            "package at https://github.com/scipy/scipy version 1.11."
        )
        self.assertNotIn(FEATURE_SHARED_CODE, observed)

    def test_explicit_osf_preregistration(self) -> None:
        observed = features(
            "The hypotheses and analysis plan were preregistered before data "
            "collection at https://osf.io/abc12/."
        )
        self.assertIn(FEATURE_PREREGISTERED, observed)

    def test_other_study_preregistration_mention_is_not_focal(self) -> None:
        observed = features(
            "A previous study by Smith was preregistered at "
            "https://osf.io/abc12/ and reported a similar result."
        )
        self.assertNotIn(FEATURE_PREREGISTERED, observed)

    def test_negated_preregistration_is_not_positive(self) -> None:
        observed = features("This study was not preregistered.")
        self.assertNotIn(FEATURE_PREREGISTERED, observed)

    def test_positive_preregistration_survives_later_negated_exploratory_analysis(self) -> None:
        observed = features(
            "The study hypotheses and analysis plan were preregistered at "
            "https://osf.io/abc12/. Exploratory analyses were not preregistered."
        )
        self.assertIn(FEATURE_PREREGISTERED, observed)

    def test_bibliography_resource_is_not_asserted(self) -> None:
        observed = features(
            "<ref-list><mixed-citation>Dataset available at "
            "https://doi.org/10.5061/dryad.abc123.</mixed-citation></ref-list>"
        )
        self.assertNotIn(FEATURE_OPEN_DATA, observed)

    def test_data_statement_immediately_before_references_is_not_bibliography(self) -> None:
        observed = features(
            "<head>Data availability</head>"
            "The data supporting the findings are publicly available at "
            "https://doi.org/10.5061/dryad.abc123."
            "<ref-list><mixed-citation>References begin here.</mixed-citation></ref-list>"
        )
        self.assertIn(FEATURE_OPEN_DATA, observed)

    def test_spaced_repository_doi_is_reconstructed(self) -> None:
        assertions, _ = extract(
            "<head>Data availability</head>"
            "Raw data generated in this study are available at "
            "https://doi.org/10. 5281/zenodo. 806176."
        )
        data_rows = [
            row for row in assertions if row["feature"] == FEATURE_OPEN_DATA
        ]
        self.assertTrue(data_rows)
        self.assertEqual(data_rows[0]["identifier"], "10.5281/zenodo.806176")

    def test_osf_preprint_doi_is_not_an_open_data_resource(self) -> None:
        observed = features(
            "The manuscript was uploaded as a preprint to OSF at "
            "https://doi.org/10.31234/osf.io/tmeb3."
        )
        self.assertNotIn(FEATURE_OPEN_DATA, observed)

    def test_malformed_url_is_ignored(self) -> None:
        observed = features(
            "Data are described at https://github.com/[malformed and nowhere else."
        )
        self.assertNotIn(FEATURE_OPEN_DATA, observed)
        self.assertNotIn(FEATURE_SHARED_CODE, observed)

    def test_prospective_date_comparison_requires_unambiguous_order(self) -> None:
        self.assertTrue(prospective_registration("2017-01-01", "2017-03-01"))
        self.assertFalse(prospective_registration("2017-04-01", "2017-03"))
        self.assertIsNone(prospective_registration("2017-03-15", "2017-03"))
        self.assertIsNone(prospective_registration("", "2017-03-01"))

    def test_review_article_does_not_inherit_included_trial_chip(self) -> None:
        assertions, _ = extract(
            "Trial registration number: NCT01234567."
        )
        import pandas as pd

        scope = pd.DataFrame(
            [
                {
                    "doi": DOI,
                    "study_title": "A systematic review of treatments",
                    "publication_type": "Journal Article | Systematic Review",
                }
            ]
        )
        kept, stats = apply_publication_semantic_guards(scope, assertions)
        self.assertFalse(
            any(row["feature"] == FEATURE_REGISTERED_TRIAL for row in kept)
        )
        self.assertEqual(stats["suppressed_review_trial_papers"], 1)


if __name__ == "__main__":
    unittest.main()
