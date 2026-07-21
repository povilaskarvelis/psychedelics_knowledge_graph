import pandas as pd

from pipeline.fulltext.prepare_browser_doi_batch import prepare_batch


def test_prepare_batch_skips_every_previously_assigned_doi() -> None:
    queue = pd.DataFrame(
        [
            {"doi": "10.1/partial", "study_title": "Partial"},
            {"doi": "10.1/new-a", "study_title": "New A"},
            {"doi": "10.1/new-b", "study_title": "New B"},
        ]
    )
    progress = pd.DataFrame(
        [
            {
                "doi": "10.1/partial",
                "study_title": "Partial",
                "browser_batch": 4,
                "manual_status": "partial_review_rate_limited",
                "manual_notes": "Resume later",
            }
        ]
    )

    batch, reservations = prepare_batch(queue, progress, batch_size=2)

    assert batch["doi"].tolist() == ["10.1/new-a", "10.1/new-b"]
    assert reservations["browser_batch"].tolist() == [5, 5]
    assert set(reservations["manual_status"]) == {"opened_for_manual_review"}


def test_prepare_batch_round_robins_doi_prefixes() -> None:
    queue = pd.DataFrame(
        [
            {"doi": "10.1016/a", "study_title": "Elsevier A"},
            {"doi": "10.1016/b", "study_title": "Elsevier B"},
            {"doi": "10.1016/c", "study_title": "Elsevier C"},
            {"doi": "10.1007/a", "study_title": "Springer A"},
            {"doi": "10.1002/a", "study_title": "Wiley A"},
        ]
    )

    batch, _ = prepare_batch(queue, pd.DataFrame(), batch_size=4, batch_number=1)

    assert batch["doi"].tolist() == ["10.1016/a", "10.1007/a", "10.1002/a", "10.1016/b"]


def test_prepare_batch_can_skip_a_reconstructed_reviewed_head() -> None:
    queue = pd.DataFrame(
        [
            {"doi": "10.1000/a", "study_title": "A"},
            {"doi": "10.2000/b", "study_title": "B"},
            {"doi": "10.3000/c", "study_title": "C"},
        ]
    )

    batch, _ = prepare_batch(
        queue,
        pd.DataFrame(),
        batch_size=1,
        batch_number=3,
        skip_unseen=2,
    )

    assert batch["doi"].tolist() == ["10.3000/c"]
