"""Results are append-only records, each carrying the provenance of the run that produced it."""

import json

from warrant.store.results import Provenance, append, config_hash

PROVENANCE = Provenance(
    config_hash="0" * 64,
    repo_commit="abc1234",
    model="anthropic.claude-model-placeholder",
    prompt_version="1",
)


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_every_stored_result_carries_the_model_name_and_the_prompt_version(tmp_path):
    path = tmp_path / "results" / "results.jsonl"
    append(path, PROVENANCE, {"question_id": "open-orders", "response_class": "correct"})

    (record,) = read(path)
    assert record["model"] == "anthropic.claude-model-placeholder"
    assert record["prompt_version"] == "1"
    assert record["config_hash"] == "0" * 64
    assert record["repo_commit"] == "abc1234"
    assert record["timestamp"]
    assert record["question_id"] == "open-orders"


def test_records_are_appended_and_never_rewritten(tmp_path):
    path = tmp_path / "results.jsonl"
    append(path, PROVENANCE, {"question_id": "open-orders"})
    first_line = path.read_text()
    append(path, PROVENANCE, {"question_id": "closed-cost"})

    assert path.read_text().startswith(first_line)
    assert [r["question_id"] for r in read(path)] == ["open-orders", "closed-cost"]


def test_the_configuration_hash_follows_the_configuration_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("runs: 1\n")
    before = config_hash(path)
    assert len(before) == 64
    assert before == config_hash(path)

    path.write_text("runs: 2\n")
    assert before != config_hash(path)
