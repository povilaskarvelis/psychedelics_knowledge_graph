import pandas as pd
import pytest

from pipeline.update.run_literature_update import Update


def make_update(tmp_path, scope):
    update = Update("living_update_test", "python")
    update.dir = tmp_path
    update.baseline = tmp_path / "baseline"
    update.baseline.mkdir()
    update.scope = tmp_path / "scope_dois.txt"
    update.scope.write_text("".join(doi + "\n" for doi in scope))
    return update


def test_update_rows_replace_only_the_update_papers(tmp_path):
    update = make_update(tmp_path, ["10.1/new"])
    table = tmp_path / "paper_domain_routing.parquet"
    before = pd.DataFrame({"doi": ["10.1/old", "10.1/new"], "domain_route": ["a", "a"], "value": [1, 0]})
    before.to_parquet(update.baseline / table.name, index=False)
    before.to_parquet(table, index=False)
    increment = tmp_path / "increment.parquet"
    pd.DataFrame({"doi": ["10.1/new", "10.1/new"], "domain_route": ["a", "b"], "value": [2, 3]}).to_parquet(increment, index=False)

    update.replace_scope_rows(table, increment, ["doi", "domain_route"])

    after = pd.read_parquet(table).sort_values(["doi", "domain_route"]).reset_index(drop=True)
    assert after.to_dict("records") == [
        {"doi": "10.1/new", "domain_route": "a", "value": 2},
        {"doi": "10.1/new", "domain_route": "b", "value": 3},
        {"doi": "10.1/old", "domain_route": "a", "value": 1},
    ]


def test_a_changed_row_outside_the_update_stops_the_replacement(tmp_path):
    update = make_update(tmp_path, ["10.1/new"])
    table = tmp_path / "paper_domain_routing.parquet"
    pd.DataFrame({"doi": ["10.1/old"], "domain_route": ["a"], "value": [1]}).to_parquet(update.baseline / table.name, index=False)
    pd.DataFrame({"doi": ["10.1/old"], "domain_route": ["a"], "value": [9]}).to_parquet(table, index=False)
    increment = tmp_path / "increment.parquet"
    pd.DataFrame({"doi": ["10.1/new"], "domain_route": ["a"], "value": [2]}).to_parquet(increment, index=False)

    with pytest.raises(AssertionError):
        update.replace_scope_rows(table, increment, ["doi", "domain_route"])
    assert pd.read_parquet(table)["value"].tolist() == [9]
