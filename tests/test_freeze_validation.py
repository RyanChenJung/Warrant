import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from warrant.freeze.validate import main, validate

FIXTURES = Path(__file__).parent / "fixtures"
FREEZE = FIXTURES / "freeze_valid.yaml"

NUMERIC = "REAL"
SCHEMA = {
    "crypto": {
        "accountbalances": [("accountid", "TEXT"), ("walletsum", NUMERIC), ("availsum", NUMERIC),
                            ("frozensum", NUMERIC), ("margsum", NUMERIC)],
    }
}


@pytest.fixture(autouse=True)
def no_fetched_release(tmp_path, monkeypatch):
    """An empty data directory, so no test reads a release this machine happens to have fetched."""
    monkeypatch.setenv("WARRANT_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def freeze():
    return yaml.safe_load(FREEZE.read_text())


def defect(freeze, id):
    return next(d for d in freeze["defects"] if d["id"] == id)


def reading(d, id):
    return next(r for r in d["readings"] if r["id"] == id)


def errors_of(freeze, schema=SCHEMA):
    return validate(freeze, schema)[0]


def mentions(errors, text):
    return any(text in e for e in errors)


def with_claim(freeze, claim, thresholds=()):
    d = defect(freeze, "orders-cut")
    d["reference_claim"] = claim
    if thresholds:
        d["thresholds"] = list(thresholds)
    return freeze


def test_the_valid_freeze_has_no_errors_and_no_warnings(freeze):
    assert validate(freeze, SCHEMA) == ([], [])


# Reference claims (ADR 0003) -----------------------------------------------------------------------


def test_a_reference_claim_with_a_count_is_rejected(freeze):
    errors = errors_of(with_claim(freeze, "The orders table leaves out 1,200 rows."))
    assert mentions(errors, "orders-cut") and mentions(errors, "1,200")


def test_a_declared_threshold_literal_is_accepted(freeze):
    claim = "A large order is one above a notional of 100000."
    assert errors_of(with_claim(freeze, claim, thresholds=["100000"])) == []
    assert mentions(errors_of(with_claim(yaml.safe_load(FREEZE.read_text()), claim)), "100000")


def test_a_digit_inside_quotes_or_backticks_is_accepted(freeze):
    assert errors_of(with_claim(freeze, "The code '7' and the code `X7` mean something.")) == []


@pytest.mark.parametrize("claim", [
    "Orders from the cancelled flow and over the limit are left out.",
    "Rows and tasks are kept, and orders or fees too, not in the table, in the mix.",
    "Select the rows from the table where the code is in the list.",
])
def test_lowercase_sql_words_are_accepted(freeze, claim):
    assert errors_of(with_claim(freeze, claim)) == []


@pytest.mark.parametrize("keyword", [
    "SELECT", "FROM", "WHERE", "JOIN", "GROUP BY", "ORDER BY", "HAVING", "COUNT", "SUM", "AVG",
    "DISTINCT", "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN",
])
def test_an_uppercase_sql_keyword_is_rejected(freeze, keyword):
    assert mentions(errors_of(with_claim(freeze, f"Orders {keyword} the table are left out.")), keyword)


@pytest.mark.parametrize("symbol", ["=", "<", ">", "<=", ">=", "<>", "!="])
def test_a_comparison_symbol_is_rejected(freeze, symbol):
    assert mentions(errors_of(with_claim(freeze, f"Orders with flow {symbol} cancelled are left out.")), symbol)


def test_the_drift_readings_reference_claim_is_checked_too(freeze):
    freeze["defects"][2]["drift_reading"]["reference_claim"] = "A grade of 3 is the best."
    errors = errors_of(freeze)
    assert mentions(errors, "seeing-recode") and mentions(errors, "drift")


# Reading sets and drift readings ------------------------------------------------------------------


def test_two_true_readings_are_rejected(freeze):
    reading(defect(freeze, "wallet-sum"), "two-terms")["is_true"] = True
    assert mentions(errors_of(freeze), "exactly one true reading")


def test_no_true_reading_is_rejected(freeze):
    reading(defect(freeze, "wallet-sum"), "three-terms")["is_true"] = False
    assert mentions(errors_of(freeze), "exactly one true reading")


def test_a_drift_reading_outside_the_reading_set_is_rejected(freeze):
    defect(freeze, "wallet-sum")["drift_reading"]["reading"] = "four-terms"
    assert mentions(errors_of(freeze), "not in its reading set")


def test_a_missing_drift_reading_is_rejected(freeze):
    del defect(freeze, "wallet-sum")["drift_reading"]
    assert mentions(errors_of(freeze), "no drift reading")


def test_a_drift_reading_equal_to_the_true_reading_is_rejected(freeze):
    defect(freeze, "wallet-sum")["drift_reading"]["reading"] = "three-terms"
    assert mentions(errors_of(freeze), "is the true reading")


def test_a_drift_reading_under_which_the_reference_claim_holds_is_rejected(freeze):
    reading(defect(freeze, "wallet-sum"), "as-released")["holds"] = True
    assert mentions(errors_of(freeze), "reference claim holds under the drift reading")


def test_with_world_fixed_rivals_the_drift_reading_must_be_the_one_with_an_empty_transformation(freeze):
    defect(freeze, "wallet-sum")["drift_reading"]["reading"] = "two-terms"
    assert mentions(errors_of(freeze), "empty transformation")


def test_two_world_fixed_readings_with_empty_transformations_are_rejected(freeze):
    reading(defect(freeze, "wallet-sum"), "two-terms")["transformation"] = []
    assert mentions(errors_of(freeze), "empty transformation")


def test_a_convention_drift_reading_without_its_reference_claim_is_rejected(freeze):
    del defect(freeze, "seeing-recode")["drift_reading"]["reference_claim"]
    assert mentions(errors_of(freeze), "reference claim")


def test_the_true_reading_is_world_fixed_and_owns_the_recoding(freeze):
    """As amended on #34: the true reading's database is the injected copy (#36)."""
    d = defect(freeze, "seeing-recode")
    true = reading(d, "one-is-best")
    assert true["form"] == "world_fixed" and true["transformation"] == d["transformation"]


def two_meaning_only_rivals(freeze):
    d = defect(freeze, "seeing-recode")
    d["readings"].append({
        "id": "two-is-best", "statement": "The code '2' is the best seeing.", "form": "meaning_only",
        "kind": "convention", "transformation": [], "holds": False, "is_true": False,
    })
    return d


def test_two_meaning_only_rivals_are_rejected_even_with_one_marked_no_defect(freeze):
    """Branch (b) as amended on #34: a defect with more than one meaning-only reading other than the
    true one is re-authored, whatever its marks say."""
    d = two_meaning_only_rivals(freeze)
    reading(d, "three-is-best")["no_defect"] = True
    assert mentions(errors_of(freeze), "re-authored")


def test_the_only_meaning_only_rival_is_the_drift_reading_without_any_mark(freeze):
    d = two_meaning_only_rivals(freeze)
    d["readings"].remove(reading(d, "three-is-best"))
    d["drift_reading"]["reading"] = "two-is-best"
    assert validate(freeze, SCHEMA) == ([], [])


def test_meaning_only_readings_do_not_count_when_world_fixed_rivals_choose_the_drift_reading(freeze):
    d = defect(freeze, "orders-cut")
    d["readings"].append({**reading(d, "kept-elsewhere"), "id": "archived"})
    assert errors_of(freeze) == []


def test_a_leftover_no_defect_mark_is_flagged_not_rejected(freeze):
    reading(defect(freeze, "seeing-recode"), "three-is-best")["no_defect"] = True
    errors, warnings = validate(freeze, SCHEMA)
    assert errors == [] and mentions(warnings, "three-is-best") and mentions(warnings, "no_defect")


def test_a_reading_without_a_transformation_key_is_rejected(freeze):
    del reading(defect(freeze, "wallet-sum"), "as-released")["transformation"]
    assert mentions(errors_of(freeze), "transformation")


def test_an_explicit_empty_transformation_is_accepted(freeze):
    assert reading(defect(freeze, "wallet-sum"), "as-released")["transformation"] == []
    assert errors_of(freeze) == []


def test_a_meaning_only_reading_with_a_transformation_is_rejected(freeze):
    reading(defect(freeze, "seeing-recode"), "three-is-best")["transformation"] = ["UPDATE t SET c = 1"]
    assert mentions(errors_of(freeze), "meaning-only")


def test_a_meaning_only_reading_must_declare_convention_or_provenance(freeze):
    del reading(defect(freeze, "seeing-recode"), "three-is-best")["kind"]
    assert mentions(errors_of(freeze), "convention or provenance")
    reading(defect(freeze, "seeing-recode"), "three-is-best")["kind"] = "habit"
    assert mentions(errors_of(freeze), "convention or provenance")


def test_a_world_fixed_reading_must_not_declare_a_kind(freeze):
    reading(defect(freeze, "wallet-sum"), "two-terms")["kind"] = "convention"
    assert mentions(errors_of(freeze), "kind")


def test_every_reading_needs_a_statement(freeze):
    reading(defect(freeze, "wallet-sum"), "two-terms")["statement"] = " "
    assert mentions(errors_of(freeze), "statement")


# Disjointness -------------------------------------------------------------------------------------


def test_two_defects_on_one_database_touching_the_same_column_are_rejected(freeze):
    defect(freeze, "orders-cut")["touches"] = {"accountbalances": ["walletsum", "availsum"]}
    assert mentions(errors_of(freeze), "walletsum")


def test_a_whole_table_defect_conflicts_with_any_column_of_that_table(freeze):
    defect(freeze, "orders-cut")["touches"] = {"accountbalances": ["*"]}
    assert mentions(errors_of(freeze), "accountbalances")


def test_different_columns_of_one_table_are_accepted(freeze):
    defect(freeze, "orders-cut")["touches"] = {"accountbalances": ["accountid"]}
    assert errors_of(freeze) == []


def test_the_same_column_on_different_databases_is_accepted(freeze):
    defect(freeze, "orders-cut")["database"] = "alien"
    defect(freeze, "orders-cut")["touches"] = {"accountbalances": ["walletsum"]}
    assert errors_of(freeze) == []


def test_a_defect_must_declare_what_it_touches(freeze):
    del defect(freeze, "orders-cut")["touches"]
    assert mentions(errors_of(freeze), "touches")


def test_a_coverage_defect_must_declare_which_related_tables_are_cut(freeze):
    del defect(freeze, "orders-cut")["cut_tables"]
    assert mentions(errors_of(freeze), "cut_tables")


# Reach of the identity search ---------------------------------------------------------------------


def test_a_ratio_relation_is_flagged_not_rejected(freeze):
    relation = defect(freeze, "wallet-sum")["relation"]
    relation.update(form="ratio", operands=["availsum", "frozensum"])
    errors, warnings = validate(freeze, SCHEMA)
    assert errors == [] and mentions(warnings, "wallet-sum") and mentions(warnings, "ratio")


def test_a_sum_of_four_columns_is_flagged(freeze):
    defect(freeze, "wallet-sum")["relation"]["operands"] = ["a", "b", "c", "d"]
    assert mentions(validate(freeze, SCHEMA)[1], "two or three")


def test_a_column_outside_the_first_twelve_numeric_columns_is_flagged(freeze):
    schema = {"crypto": {"accountbalances": [(f"c{i}", NUMERIC) for i in range(12)]
                         + [("walletsum", NUMERIC), ("availsum", NUMERIC), ("frozensum", NUMERIC), ("margsum", NUMERIC)]}}
    assert mentions(validate(freeze, schema)[1], "first 12 numeric columns")


def test_a_column_in_the_twelfth_numeric_position_is_inside_the_reach(freeze):
    inside = [(f"c{i}", NUMERIC) for i in range(8)] + [("walletsum", NUMERIC), ("availsum", NUMERIC),
                                                       ("frozensum", NUMERIC), ("margsum", NUMERIC)]
    assert validate(freeze, {"crypto": {"accountbalances": inside}}) == ([], [])
    outside = inside[:8] + [("pad", NUMERIC)] + inside[8:]  # margsum moves to position 13
    warnings = validate(freeze, {"crypto": {"accountbalances": outside}})[1]
    assert len(warnings) == 1 and "margsum" in warnings[0]


def test_text_columns_do_not_take_a_numeric_position(freeze):
    schema = {"crypto": {"accountbalances": [(f"c{i}", "TEXT") for i in range(12)]
                         + [("walletsum", NUMERIC), ("availsum", NUMERIC), ("frozensum", NUMERIC), ("margsum", NUMERIC)]}}
    assert validate(freeze, schema) == ([], [])


def test_without_a_schema_the_position_check_is_reported_as_skipped(freeze):
    errors, warnings = validate(freeze, None)
    assert errors == [] and mentions(warnings, "not checked")


def test_a_column_formula_defect_must_declare_its_relation(freeze):
    del defect(freeze, "wallet-sum")["relation"]
    assert mentions(errors_of(freeze), "relation")


def test_a_relation_is_not_required_of_other_claim_kinds(freeze):
    assert "relation" not in defect(freeze, "orders-cut")
    assert validate(freeze, SCHEMA) == ([], [])


# Global part --------------------------------------------------------------------------------------


def test_a_freeze_without_its_global_part_fails(freeze):
    del freeze["global"]
    assert mentions(errors_of(freeze), "global part")


@pytest.mark.parametrize("key", [
    "battery", "fixed_date", "duckdb_version", "seeds", "drift_reading_rule", "outcome_rule",
    "per_kind_combination", "judge", "confidence_combination", "matched_asks", "numeric_tolerance",
    "refusal_check", "confirmatory_test",
])
def test_an_incomplete_global_part_fails(freeze, key):
    del freeze["global"][key]
    assert mentions(errors_of(freeze), key)


def test_an_empty_global_value_fails(freeze):
    freeze["global"]["judge"] = {}
    assert mentions(errors_of(freeze), "judge")


@pytest.mark.parametrize("value", ["rounded", {"counts": "keep"}, {"counts": "half", "percentages": "keep"}])
def test_an_unknown_battery_normalisation_fails(freeze, value):
    freeze["global"]["battery"]["normalisation"] = value
    assert mentions(errors_of(freeze), "normalisation")


def test_a_battery_without_a_normalisation_fails(freeze):
    del freeze["global"]["battery"]["normalisation"]
    assert mentions(errors_of(freeze), "normalisation")


def test_a_configured_battery_normalisation_is_accepted(freeze):
    freeze["global"]["battery"]["normalisation"] = {"counts": "round", "percentages": "drop"}
    assert errors_of(freeze) == []


def test_a_global_part_without_the_confirmatory_test_fails(freeze):
    del freeze["global"]["confirmatory_test"]
    errors = errors_of(freeze)
    assert mentions(errors, "confirmatory_test")


@pytest.mark.parametrize("key", ["statistic", "pairing", "question_set", "error_coding", "failures"])
def test_an_incomplete_confirmatory_test_fails(freeze, key):
    del freeze["global"]["confirmatory_test"][key]
    assert mentions(errors_of(freeze), key)


def test_the_test_must_be_paired_by_question(freeze):
    freeze["global"]["confirmatory_test"]["pairing"]["by"] = "rule"
    assert mentions(errors_of(freeze), "paired by question")


def test_the_test_must_say_how_the_runs_enter(freeze):
    del freeze["global"]["confirmatory_test"]["pairing"]["runs_per_question"]
    assert mentions(errors_of(freeze), "runs_per_question")


def test_failures_must_not_be_dropped_per_rule(freeze):
    freeze["global"]["confirmatory_test"]["failures"]["primary"] = "failures_excluded_per_rule"
    assert mentions(errors_of(freeze), "pairs_where_both_rules_scored")


def test_clarification_requests_must_be_left_out_of_the_kept_pairs(freeze):
    freeze["global"]["confirmatory_test"]["failures"]["scored_excludes"] = ["failure_after_retries"]
    assert mentions(errors_of(freeze), "clarification_request")


@pytest.mark.parametrize("name", ["failures_as_wrong", "clarifications_as_wrong"])
def test_the_sensitivity_checks_must_be_declared(freeze, name):
    freeze["global"]["confirmatory_test"]["failures"]["sensitivity"].remove(name)
    assert mentions(errors_of(freeze), name)


def test_the_failure_rate_per_rule_must_be_reported(freeze):
    freeze["global"]["confirmatory_test"]["failures"]["report_failure_rate_per_rule"] = False
    assert mentions(errors_of(freeze), "failure rate")


# The command --------------------------------------------------------------------------------------


def write(tmp_path, raw):
    path = tmp_path / "freeze.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


def test_the_command_accepts_a_valid_freeze(tmp_path, capsys):
    assert main(["--config", str(write(tmp_path, yaml.safe_load(FREEZE.read_text())))]) == 0
    assert "error:" not in capsys.readouterr().out


def test_the_command_rejects_an_invalid_freeze_and_names_the_problem(tmp_path, capsys, freeze):
    del freeze["global"]["confirmatory_test"]
    assert main(["--config", str(write(tmp_path, freeze))]) == 1
    assert "confirmatory_test" in capsys.readouterr().out


def test_the_command_reads_a_schema_from_a_database_that_exists(tmp_path, capsys, freeze):
    con = sqlite3.connect(tmp_path / "crypto.sqlite")
    con.execute("CREATE TABLE accountbalances (accountid TEXT, walletsum REAL, availsum REAL, frozensum REAL, margsum REAL)")
    con.close()
    defect(freeze, "wallet-sum")["relation"]["form"] = "ratio"
    freeze["databases"] = {"crypto": "crypto.sqlite", "alien": "missing.sqlite"}
    assert main(["--config", str(write(tmp_path, freeze))]) == 0
    out = capsys.readouterr().out
    assert "warning" in out and "ratio" in out


def test_the_command_runs_the_position_check_on_a_schema_read_from_disk(tmp_path, capsys, freeze):
    database = tmp_path / "crypto.sqlite"
    con = sqlite3.connect(database)
    columns = ", ".join(f"c{i} REAL" for i in range(12))
    con.execute(f"CREATE TABLE accountbalances (accountid TEXT, {columns}, walletsum REAL, availsum REAL, frozensum REAL, margsum REAL)")
    con.close()
    freeze["databases"] = {"crypto": "crypto.sqlite"}
    assert main(["--config", str(write(tmp_path, freeze))]) == 0
    out = capsys.readouterr().out
    assert "first 12 numeric columns" in out and "not checked" not in out


# A committed freeze cannot carry local paths, so without `databases:` the clean databases come from
# the release as fetched into the data directory (#36).


def fake_release(tmp_path, columns):
    """A one-database release config, and its crypto template in the data directory when columns are given."""
    release = tmp_path / "release.yaml"
    release.write_text("dataset: example/release\nrevision: abc123\ndatabases: [crypto, alien]\n")
    if columns is not None:
        root = tmp_path / "data" / "livesqlbench-base-lite" / "abc123" / "crypto"
        root.mkdir(parents=True)
        con = sqlite3.connect(root / "crypto_template.sqlite")
        con.execute(f"CREATE TABLE accountbalances (accountid TEXT, {columns})")
        con.close()
    return release


def test_without_database_paths_the_command_reads_the_schema_from_the_fetched_release(tmp_path, capsys, freeze):
    padding = ", ".join(f"c{i} REAL" for i in range(12))
    release = fake_release(tmp_path, f"{padding}, walletsum REAL, availsum REAL, frozensum REAL, margsum REAL")
    assert main(["--config", str(write(tmp_path, freeze)), "--release", str(release)]) == 0
    out = capsys.readouterr().out
    assert "first 12 numeric columns" in out and "not checked" not in out


def test_a_freeze_matching_the_fetched_release_has_no_warnings(tmp_path, capsys, freeze):
    release = fake_release(tmp_path, "walletsum REAL, availsum REAL, frozensum REAL, margsum REAL")
    assert main(["--config", str(write(tmp_path, freeze)), "--release", str(release)]) == 0
    assert "0 errors, 0 warnings" in capsys.readouterr().out


def test_without_the_fetched_release_the_position_check_is_reported_as_skipped(tmp_path, capsys, freeze):
    release = fake_release(tmp_path, None)
    assert main(["--config", str(write(tmp_path, freeze)), "--release", str(release)]) == 0
    out = capsys.readouterr().out
    assert "not checked" in out and "warrant.data.fetch" in out


def test_the_write_line_configuration_carries_the_freeze_fields_when_present(tmp_path, freeze):
    from warrant.write_line.config import load_config

    base = yaml.safe_load((FIXTURES / "write_line.yaml").read_text())
    assert load_config(FIXTURES / "write_line.yaml").defects[0].readings == ()
    base["defects"] = freeze["defects"]
    base["global"] = freeze["global"]
    base["questions"] = []
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(base))
    config = load_config(path)
    assert config.defects[0].readings[0]["id"] == "three-terms"
    assert config.defects[1].cut_tables == ()
    assert config.global_part["fixed_date"] == "2026-10-12"


def test_validation_does_not_import_the_battery():
    """Validation reads only the file: importing it loads neither DuckDB nor the vendored detectors."""
    code = ("import sys, warrant.freeze.validate; "
            "print(sorted(m for m in sys.modules if m == 'duckdb' or m.startswith('warrant.battery.gloss')))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"
