"""Current Luna event/category and exposure contracts, including negative controls."""
import pytest
from pipeline.kg import build_evidence_tables as b


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


@pytest.mark.parametrize("event,category", [
    ("Headaches after treatment", "Headache"),
    ("Hepatotoxicity", "Hepatic toxicity"),
    ("Convulsive activity", "Seizure/convulsion"),
    ("Valvular heart disease", "Cardiovascular safety"),
    ("Adverse-event risk", "Adverse events"),
    ("No serious side effects were recorded", "Serious adverse events"),
    ("Discontinuation for any reason", "All-cause discontinuation"),
    ("Addiction and dependence potential", "Abuse/dependence liability"),
    ("Reductions in plasma sodium and plasma osmolality associated with CYP2D6 genotype", "Electrolyte/fluid balance"),
    ("No hyponatraemia was reported", "Electrolyte/fluid balance"),
])
def test_event_inflections_and_null_events_keep_their_existing_family(event, category):
    assert b.safety_category_for_text(event) == category


def test_legacy_drug_and_enzyme_keywords_do_not_override_the_measured_event():
    assert b.safety_endpoint_label({
        "safety_event_or_measure": "Withdrawal from study after adverse effects during paroxetine pretreatment",
        "safety_category": "discontinuation due to adverse events",
    }) == "Discontinuation due to adverse events"
    assert b.safety_endpoint_label({"safety_event_or_measure": "moclobemide",
                                    "safety_category": "serotonin syndrome"}) == "Serotonin syndrome"
    assert b.safety_endpoint_label({"safety_event_or_measure": "−2.31 ± 0.84 °C in Tg-CYP2D6 mice",
                                    "safety_category": "Thermoregulatory safety"}) == "Body temperature effects"
    assert b.safety_category_for_text("paroxetine") == ""
    assert b.safety_category_for_text("Inhibition of CYP2D6 activity") == ""
    assert b.safety_category_for_text("Drug interaction between MDMA and paroxetine co-administration") == "Drug interaction risk"


def test_neutral_electrolyte_anchor_does_not_invent_a_confirmed_diagnosis():
    row = {"safety_event_or_measure": "Reductions in plasma sodium and plasma osmolality",
           "safety_category": "electrolyte imbalance / hyponatraemia",
           "finding_summary": "Changes were associated with genotype; the abstract discusses possible hyponatraemia risk, not confirmed cases."}
    assert b.safety_endpoint_label(row) == "Electrolyte/fluid balance"
    assert row["finding_summary"].endswith("not confirmed cases.")


def test_arrhythmia_uses_the_existing_specific_anchor():
    assert b.safety_specific_endpoint_label({"safety_event_or_measure": "Arrhythmia"}, "Cardiovascular safety") == "Arrhythmia risk"


def test_addiction_treatment_is_not_itself_an_abuse_liability_endpoint():
    assert b.safety_category_for_text("Addiction treatment efficacy") == ""


@pytest.mark.parametrize("event", ["Nasal discomfort", "Injection site reactions", "Dysgeusia", "Transient tingling"])
def test_explicit_event_and_declared_family_do_not_require_a_regex_for_every_event(event, registry):
    row = {"safety_event_or_measure": event, "safety_category": "general tolerability/adverse events"}
    match = b.graphable_entity_match(row, "safety_tolerability", "safety_adverse_event", event, registry, {})
    assert match["label"] == "Adverse events"
    assert match["match_type"] != "unmapped_safety_endpoint_detail_only"
    assert b.safety_endpoint_label(row) == "Adverse events"
    # The exact event survives without creating an uncontrolled prose node.
    assert b.safety_specific_endpoint_label(row, "Adverse events") == "Adverse events"
    assert row["safety_event_or_measure"] == event


@pytest.mark.parametrize("row", [
    {"safety_event_or_measure": "Nasal discomfort", "safety_category": "unvalidated family"},
    {"safety_event_or_measure": "Nasal discomfort", "support": "Renal function was monitored"},
    {"safety_event_or_measure": "Safety concerns", "safety_category": "general tolerability/adverse events"},
    {"safety_event_or_measure": "Nasal discomfort; monitoring practices may be incorrect", "safety_category": "Adverse events"},
    {"safety_event_or_measure": "not reported", "safety_category": "Adverse events"},
])
def test_untyped_or_non_result_prose_is_not_admitted_by_a_declared_pair(row):
    assert b.declared_safety_event_category(row) == ("", "")


@pytest.mark.parametrize("exposure,canonical", [
    ("Ketamine exposure", "Ketamine"),
    ("Supervised clinical MDMA", "MDMA"),
    ("Ayahuasca intake", "Ayahuasca"),
    ("Recreational ketamine abuse", "Ketamine"),
])
def test_neutral_exposure_wrappers_preserve_registered_identity(exposure, canonical, registry):
    row = {"compound": exposure, "source_type": "review", "source_family": "secondary_literature",
           "graph_subject_kind": "exposure_context", "domain": "safety_tolerability"}
    match = b.graphable_subject_match(row, registry)
    subjects = b.overview_graph_subjects(row, match, registry)
    assert [s["label"] for s in subjects] == [canonical]
    assert row["compound"] == exposure


@pytest.mark.parametrize("exposure", [
    "Ketamine and esketamine exposure", "Ketamine plus unknown agent exposure",
    "6-fluoro-ketamine exposure", "Ketamine-induced bladder disease", "Ketamine exposure questionnaire",
    "Caffeine exposure", "No ketamine exposure", "Ketamine or ECT treatment",
])
def test_wrapper_parser_does_not_borrow_parent_drug_or_ignore_other_actors(exposure, registry):
    assert b.registered_exposure_wrapper_subject(exposure, registry) is None


def test_pooled_generic_psychedelic_class_remains_one_reported_statistical_unit(registry):
    row = {"compound": "Moderate-dose psychedelics", "meta_analysis_subject_scope": "intervention_class",
           "source_type": "meta_analysis", "domain": "safety_tolerability"}
    subjects = b.overview_graph_subjects(row, b.graphable_subject_match(row, registry), registry)
    assert [(s["label"], s["kind"]) for s in subjects] == [(b.BROAD_PSYCHEDELIC_CLASS_LABEL, "compound_class")]


@pytest.mark.parametrize("scope,exposure", [
    ("comparison_between_interventions", "Moderate-dose psychedelics"),
    ("pooled_multiple_interventions", "Ketamine or esketamine"),
    ("control_arm", "Psychedelics"),
    ("intervention_class", "Non-psychedelics"),
])
def test_statistical_comparisons_and_pooled_named_drugs_remain_unsplit(scope, exposure, registry):
    row = {"compound": exposure, "meta_analysis_subject_scope": scope, "source_type": "meta_analysis"}
    assert b.overview_graph_subjects(row, b.graphable_subject_match(row, registry), registry) == []


def test_current_safety_dimensions_are_structured_normalized_fields():
    values = {"safety_event_or_measure": "Nasal discomfort", "safety_category": "Adverse events",
              "severity": "Mild", "seriousness": "Non-serious", "frequency_or_rate": "3/45",
              "discontinuation_or_withdrawal": "None due to this event"}
    row = {"study_doi": "10.example/safety", "compound": "Ketamine", **values}
    result = b.finding_row(row, "test", "safety_tolerability", "safety_tolerability", "primary_evidence",
                           "finding-test", "paper-test", id_field="finding_id")
    for key, value in values.items():
        assert result[key] == value


def test_explicit_human_review_is_not_removed_by_event_or_exposure_mapping():
    row = {"domain": "safety_tolerability", "graph_admission_status": "paper_detail",
           "graph_admission_reason": "extraction_marked_for_human_review",
           "safety_event_or_measure": "Nasal discomfort", "safety_category": "Adverse events"}
    assert b.graph_admission_decision(row) == ("paper_detail", "extraction_marked_for_human_review")


@pytest.mark.parametrize("event,statement,extra,reason", [
    ("Quality of adverse-event reporting", "Adverse-event reporting quality varied across nine RCTs.", {}, "safety_reporting_quality_not_observed_event"),
    ("Adverse-event reporting", "Only three trials showed full concordance; most had qualitative and quantitative discrepancies.", {}, "safety_reporting_quality_not_observed_event"),
    ("Reported adverse-event incidence and severity", "The authors predict that incidence may increase as trials expand.", {}, "anticipated_or_policy_safety_not_observed_event"),
    ("Perceived safety of psychedelic use under medical supervision", "This is a survey of safety perceptions, not an observed clinical safety outcome.", {}, "perceived_safety_not_observed_event"),
    ("Preference for regular clinical monitoring", "Participants advocated regular reviews to identify unknown side effects.", {}, "organizational_safety_practice_not_observed_event"),
    ("Reduced CYP1A2 enzyme activity", "Measured CYP1A2 activity decreased in medium and plasma.", {"safety_category": "Hepatotoxicity"}, "enzyme_activity_not_observed_organ_toxicity"),
    ("Withdrawal during paroxetine pretreatment", "One participant withdrew after adverse effects during the first six days of paroxetine pretreatment.", {"compound_or_exposure": "Paroxetine pretreatment in the LSD crossover trial"}, "pretreatment_phase_event_requires_actor_resolution"),
])
def test_process_predictions_and_reference_events_are_not_observed_drug_harms(event, statement, extra, reason):
    row = {"domain": "safety_tolerability", "safety_event_or_measure": event, "finding_summary": statement, **extra}
    b.current_field_role_boundary(row, "safety_tolerability")
    assert b.graph_admission_decision(row) == ("paper_detail", reason)


@pytest.mark.parametrize("event,statement,extra", [
    ("Adverse-event reporting and serious adverse events", "45% of studies did not report AEs; serious adverse events were reported in one study.", {}),
    ("Seizure monitoring, including neurological checks and EEG", "No seizures were detected during observation.", {}),
    ("No serious adverse events", "No serious adverse events occurred in the treated group.", {}),
    ("CYP1A2 activity and cell viability", "Activity decreased and significant cell death was observed.", {"safety_category": "Hepatotoxicity"}),
    ("CYP-mediated modulation of cytotoxicity", "CYP inhibition shifted the cytotoxicity concentration-response curves to the left.", {"safety_category": "hepatic toxicity"}),
    ("CYP activity and Cell Viability", "Cell Viability decreased in the exposed cell model.", {"safety_category": "hepatic toxicity"}),
    ("Nausea", "Nausea was observed in three participants; the authors predict more events in larger trials.", {}),
    ("Serious adverse events; quality of adverse-event reporting", "One participant had a serious adverse event. Reporting quality varied.", {}),
    ("Preference for monitoring and reported adverse events", "Nausea was reported by three participants during clinical monitoring.", {}),
])
def test_actual_results_nulls_and_injury_measures_are_preserved(event, statement, extra):
    row = {"domain": "safety_tolerability", "safety_event_or_measure": event, "finding_summary": statement, **extra}
    # The last contrast is an observed event, not a pure proposed procedure.
    if event.startswith("Preference"):
        row["safety_event_or_measure"] = "Nausea during clinical monitoring"
    b.current_field_role_boundary(row, "safety_tolerability")
    assert row.get("graph_admission_status") != "paper_detail"
