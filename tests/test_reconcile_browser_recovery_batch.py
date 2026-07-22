import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.reconcile_browser_recovery_batch import (
    apply_access_overrides,
    apply_progress_updates,
    merge_import_reports,
    project_access_overrides_to_candidate,
    reconcile,
)


def test_reconcile_separates_recovered_format_excluded_and_unresolved_records() -> None:
    batch = pd.DataFrame(
        [
            {"doi": "10.1/recovered"},
            {"doi": "10.1/poster"},
            {"doi": "10.1/unusable"},
        ]
    )
    import_report = {
        "imported": [
            {"doi": "10.1/recovered", "status": "matched"},
            {"doi": "10.1/extra", "status": "already_present"},
        ]
    }
    formats = {
        "records": [{"doi": "10.1/poster", "publication_format": "conference_poster"}]
    }

    outcome, report = reconcile(batch, import_report, formats)

    assert outcome[["doi", "browser_recovery_status"]].to_dict("records") == [
        {"doi": "10.1/recovered", "browser_recovery_status": "article_pdf_recovered"},
        {"doi": "10.1/poster", "browser_recovery_status": "excluded_publication_format"},
        {"doi": "10.1/unusable", "browser_recovery_status": "pending_manual_review"},
    ]
    assert report["extra_imported_dois_not_in_batch"] == ["10.1/extra"]


def test_reconcile_preserves_interrupted_records_for_later_review() -> None:
    batch = pd.DataFrame(
        [
            {
                "doi": "10.1/interrupted",
                "manual_status": "partial_review_rate_limited",
            }
        ]
    )

    outcome, report = reconcile(batch, {"imported": []}, {"records": []})

    assert outcome.loc[0, "browser_recovery_status"] == "pending_manual_review"
    assert report["status_counts"] == {"pending_manual_review": 1}


def test_reconcile_does_not_turn_completed_interrupted_records_into_closed_access() -> None:
    batch = pd.DataFrame(
        [{"doi": "10.1/completed", "manual_status": "partial_review_rate_limited"}]
    )

    outcome, report = reconcile(
        batch,
        {"imported": []},
        {"records": []},
        finalize_partial_review=True,
    )

    assert outcome.loc[0, "browser_recovery_status"] == "pending_manual_review"
    assert report["status_counts"] == {"pending_manual_review": 1}


def test_apply_progress_updates_records_terminal_batch_results(tmp_path: Path) -> None:
    progress_path = tmp_path / "progress.csv"
    pd.DataFrame(
        [
            {"doi": "10.1/recovered", "manual_status": "opened_for_manual_review", "manual_notes": ""},
            {"doi": "10.1/closed", "manual_status": "opened_for_manual_review", "manual_notes": ""},
            {"doi": "10.1/other", "manual_status": "opened_for_manual_review", "manual_notes": ""},
        ]
    ).to_csv(progress_path, index=False)
    outcome = pd.DataFrame(
        [
            {"doi": "10.1/recovered", "browser_recovery_status": "article_pdf_recovered", "browser_recovery_detail": "Imported"},
            {"doi": "10.1/closed", "browser_recovery_status": "confirmed_closed_access", "browser_recovery_detail": "Paywalled"},
        ]
    )

    changed = apply_progress_updates(progress_path, outcome)

    updated = pd.read_csv(progress_path).fillna("")
    assert changed == 2
    assert updated["manual_status"].tolist() == ["article_pdf_recovered", "closed_access", "opened_for_manual_review"]


def test_reconcile_preserves_user_directed_batch_closeout_provenance() -> None:
    batch = pd.DataFrame(
        [
            {
                "doi": "10.1/batch-closed",
                "manual_status": "batch_closed_access",
                "manual_notes": "User directed closure of the remaining low-yield queue.",
            }
        ]
    )

    outcome, report = reconcile(batch, {"imported": [], "review": []}, {"records": []})

    assert report["status_counts"] == {"batch_closed_access": 1}
    assert outcome.iloc[0]["browser_recovery_status"] == "batch_closed_access"
    assert outcome.iloc[0]["browser_recovery_detail"] == (
        "User directed closure of the remaining low-yield queue."
    )


def test_reconcile_counts_existing_pdf_conflict_as_already_recovered() -> None:
    outcome, _ = reconcile(
        pd.DataFrame([{"doi": "10.1/conflict"}]),
        {"imported": [], "review": [{"doi": "10.1/conflict", "status": "conflict_existing_pdf"}]},
        {"records": []},
    )

    assert outcome.loc[0, "browser_recovery_status"] == "article_pdf_recovered"


def test_merge_import_reports_preserves_multi_pass_imports_and_reviews() -> None:
    merged = merge_import_reports(
        [
            {"imported": [{"doi": "10.1/first", "status": "matched"}]},
            {
                "imported": [{"doi": "10.1/second", "status": "matched"}],
                "review": [{"doi": "10.1/existing", "status": "conflict_existing_pdf"}],
            },
        ]
    )

    assert [row["doi"] for row in merged["imported"]] == ["10.1/first", "10.1/second"]
    assert [row["doi"] for row in merged["review"]] == ["10.1/existing"]


def test_reconcile_classifies_repository_alias_of_recovered_canonical() -> None:
    outcome, _ = reconcile(
        pd.DataFrame([{"doi": "10.1/repository"}]),
        {"imported": [{"doi": "10.1/article", "status": "matched"}]},
        {"records": []},
        {"10.1/repository": "10.1/article"},
    )

    assert outcome.loc[0, "browser_recovery_status"] == "duplicate_of_canonical"


def test_apply_access_overrides_removes_stale_suppression_after_recovery(tmp_path: Path) -> None:
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        '{"schema_version":"manual_fulltext_access_overrides_v1","notes":[],"records":['
        '{"doi":"10.1/recovered","manual_access_action":"suppress_pdf_download","manual_reason":"old"},'
        '{"doi":"10.1/still-closed","manual_access_action":"suppress_pdf_download","manual_reason":"old"}'
        ']}'
    )
    outcome = pd.DataFrame(
        [
            {"doi": "10.1/recovered", "browser_recovery_status": "duplicate_of_canonical"},
            {"doi": "10.1/still-closed", "browser_recovery_status": "confirmed_closed_access"},
        ]
    )

    changed = apply_access_overrides(override_path, outcome)

    records = json.loads(override_path.read_text())["records"]
    assert changed == 2
    assert [record["doi"] for record in records] == ["10.1/still-closed"]


def test_apply_access_overrides_ignores_pending_and_technical_attempts(tmp_path: Path) -> None:
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        '{"schema_version":"manual_fulltext_access_overrides_v1","records":['
        '{"doi":"10.1/pending","manual_access_action":"suppress_pdf_download","manual_reason":"curated"}'
        ']}'
    )
    outcome = pd.DataFrame(
        [{"doi": "10.1/pending", "browser_recovery_status": "pending_manual_review"}]
    )

    changed = apply_access_overrides(override_path, outcome)

    assert changed == 0
    assert json.loads(override_path.read_text())["records"][0]["doi"] == "10.1/pending"


def test_project_access_overrides_updates_only_terminal_candidate_rows(tmp_path: Path) -> None:
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        '{"schema_version":"manual_fulltext_access_overrides_v1","records":['
        '{"doi":"10.1/closed","manual_access_action":"suppress_pdf_download","manual_reason":"reviewed"}'
        ']}'
    )
    candidate_path = tmp_path / "candidate.parquet"
    pd.DataFrame(
        [
            {"doi": "10.1/closed", "manual_fulltext_access_action": "", "manual_fulltext_access_reason": ""},
            {"doi": "10.1/pending", "manual_fulltext_access_action": "", "manual_fulltext_access_reason": ""},
        ]
    ).to_parquet(candidate_path, index=False)
    outcome = pd.DataFrame(
        [
            {"doi": "10.1/closed", "browser_recovery_status": "confirmed_closed_access"},
            {"doi": "10.1/pending", "browser_recovery_status": "pending_manual_review"},
        ]
    )

    changed = project_access_overrides_to_candidate(override_path, candidate_path, outcome)

    updated = pd.read_parquet(candidate_path).fillna("")
    assert changed == 1
    assert updated.loc[0, "manual_fulltext_access_action"] == "suppress_pdf_download"
    assert updated.loc[1, "manual_fulltext_access_action"] == ""
