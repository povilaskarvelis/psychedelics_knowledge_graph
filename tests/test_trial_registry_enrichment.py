import unittest

from pipeline.enrich.enrich_trial_registries import (
    build_candidates,
    enrich_registry_group,
    flat_enrichment_rows,
    group_candidates_by_registry,
    normalize_clinicaltrials_study,
    primary_source_dois,
    registry_ids_from_row,
    registry_kind,
)


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        registry_id = url.rstrip("/").split("/")[-1]
        if registry_id not in self.payloads:
            raise AssertionError(f"Unexpected registry lookup: {registry_id}")
        return self.payloads[registry_id]


class TrialRegistryEnrichmentTest(unittest.TestCase):
    def test_registry_id_detection_supports_common_registries(self) -> None:
        row = {
            "trial_registry_ids": "NCT01234567 | ISRCTN12345678 | 2020-001234-56",
            "abstract": "Also reported as ACTRN12345678901234.",
        }

        self.assertEqual(registry_kind("NCT01234567"), "clinicaltrials_gov")
        self.assertEqual(registry_kind("ISRCTN12345678"), "isrctn")
        self.assertEqual(registry_kind("2020-001234-56"), "eudract")
        self.assertEqual(registry_ids_from_row(row), [
            "NCT01234567",
            "ISRCTN12345678",
            "2020-001234-56",
            "ACTRN12345678901234",
        ])

    def test_candidates_are_screened_and_optionally_primary_filtered(self) -> None:
        paper_rows = [
            {
                "study_doi": "10.1000/a",
                "study_title": "Trial A",
                "trial_registry_ids": "NCT01234567",
            },
            {
                "study_doi": "10.1000/b",
                "study_title": "Protocol B",
                "trial_registry_ids": "NCT07654321",
            },
        ]
        screening_rows = [
            {"study_doi": "10.1000/a", "screening_relevance": "relevant", "candidate_source": "screening"},
            {"study_doi": "10.1000/b", "screening_relevance": "uncertain", "candidate_source": "screening"},
        ]
        primary_dois = primary_source_dois(
            [
                {
                    "study_doi": "10.1000/a",
                    "source_type": "primary_study",
                    "paper_type": "primary_results",
                },
                {
                    "study_doi": "10.1000/b",
                    "source_family": "protocol",
                    "source_type": "study_protocol",
                    "paper_type": "protocol",
                },
            ]
        )

        all_candidates, before = build_candidates(
            paper_db_rows=paper_rows,
            screening_rows=screening_rows,
            queue_rows=[],
            include_unscreened=False,
            require_primary_source=False,
            primary_dois=primary_dois,
        )
        primary_candidates, primary_before = build_candidates(
            paper_db_rows=paper_rows,
            screening_rows=screening_rows,
            queue_rows=[],
            include_unscreened=False,
            require_primary_source=True,
            primary_dois=primary_dois,
        )

        self.assertEqual(before, 2)
        self.assertEqual(len(all_candidates), 2)
        self.assertEqual(primary_before, 2)
        self.assertEqual([row["study_doi"] for row in primary_candidates], ["10.1000/a"])

    def test_normalizes_clinicaltrials_v2_payload(self) -> None:
        normalized = normalize_clinicaltrials_study(
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT01234567",
                        "briefTitle": "Brief trial",
                        "officialTitle": "Official trial",
                        "secondaryIdInfos": [{"id": "ABC-1"}],
                    },
                    "statusModule": {
                        "overallStatus": "COMPLETED",
                        "startDateStruct": {"date": "2020-01"},
                        "primaryCompletionDateStruct": {"date": "2021-02"},
                        "completionDateStruct": {"date": "2021-03"},
                        "lastUpdatePostDateStruct": {"date": "2022-04-05"},
                    },
                    "designModule": {
                        "studyType": "INTERVENTIONAL",
                        "phases": ["PHASE2"],
                        "enrollmentInfo": {"count": 100, "type": "ACTUAL"},
                        "designInfo": {
                            "allocation": "RANDOMIZED",
                            "interventionModel": "PARALLEL",
                            "primaryPurpose": "TREATMENT",
                            "maskingInfo": {"masking": "DOUBLE"},
                        },
                    },
                    "conditionsModule": {"conditions": ["Depression"]},
                    "armsInterventionsModule": {
                        "interventions": [{"type": "DRUG", "name": "Psilocybin"}],
                        "armGroups": [{"label": "Psilocybin arm"}],
                    },
                    "outcomesModule": {
                        "primaryOutcomes": [{"measure": "MADRS", "timeFrame": "6 weeks"}]
                    },
                    "sponsorCollaboratorsModule": {
                        "leadSponsor": {"name": "Sponsor", "class": "OTHER"},
                        "collaborators": [{"name": "Collaborator"}],
                    },
                    "eligibilityModule": {
                        "minimumAge": "18 Years",
                        "maximumAge": "65 Years",
                        "sex": "ALL",
                        "healthyVolunteers": False,
                    },
                },
                "resultsSection": {"participantFlowModule": {}},
            }
        )

        self.assertEqual(normalized["registry_id"], "NCT01234567")
        self.assertEqual(normalized["overall_status"], "COMPLETED")
        self.assertEqual(normalized["phases"], "PHASE2")
        self.assertEqual(normalized["enrollment_count"], "100")
        self.assertEqual(normalized["interventions"], "DRUG: Psilocybin")
        self.assertEqual(normalized["primary_outcomes"], "MADRS (6 weeks)")
        self.assertEqual(normalized["lead_sponsor"], "Sponsor")
        self.assertEqual(normalized["has_results"], "true")

    def test_enrichment_fetches_nct_and_reports_unsupported_registries(self) -> None:
        candidates = [
            {
                "study_doi": "10.1000/a",
                "study_title": "Trial A",
                "trial_registry_ids": "NCT01234567 | ISRCTN12345678",
                "registry_ids": ["NCT01234567", "ISRCTN12345678"],
                "compounds": "Psilocybin",
                "disorders": "Depression",
                "screening_relevance_values": "relevant",
                "candidate_sources": "screening_report",
            }
        ]
        grouped = group_candidates_by_registry(candidates)
        payload = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT01234567", "briefTitle": "Trial A"},
                "statusModule": {"overallStatus": "RECRUITING"},
                "designModule": {"studyType": "INTERVENTIONAL"},
            }
        }
        cache, events = enrich_registry_group(
            grouped=grouped,
            cache={"schema_version": "trial_registry_enrichment_v1", "registries": {}},
            client=FakeClient({"NCT01234567": payload}),
            refresh=False,
            omit_raw=True,
        )
        rows = flat_enrichment_rows(grouped, cache)
        by_id = {row["registry_id"]: row for row in rows}

        self.assertEqual({event["event"] for event in events}, {"fetched", "unsupported_registry"})
        self.assertEqual(by_id["NCT01234567"]["lookup_status"], "ok")
        self.assertEqual(by_id["NCT01234567"]["overall_status"], "RECRUITING")
        self.assertEqual(by_id["ISRCTN12345678"]["lookup_status"], "unsupported_registry")
        self.assertNotIn("raw", cache["registries"]["NCT01234567"])


if __name__ == "__main__":
    unittest.main()
