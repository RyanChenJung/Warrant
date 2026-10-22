# The judge's validation (`global.judge.validation`)

`2026-10-21-4af7c61.jsonl` holds the judge's validation, run once before any claim-writing call, as
the freeze requires. The file has 8 records: a start record, one record per validation claim, and a
completion record. Every record carries the run's provenance (repo commit `4af7c61`, the SHA-256 of
`configs/write_line_pilot.yaml`, the model and the judge's prompt version) and run id
`c34864a82ed148629b9b54d4308286a9`.

It was run on 2026-10-21 between 22:36 and 22:37 UTC with
`uv run python -m warrant.write_line.validate_judge --config configs/write_line_pilot.yaml`, from
`main` at `4af7c61`. The judge was `anthropic.claude-sonnet-5` on Amazon Bedrock in us-east-1, with
the settings committed for claim writing: effort high, thinking at the model's default, max_tokens
16000, and no sampling parameter. The rubric is `freeze/judge_rubric.md`, pinned to the freeze
commit. This is the first complete validation run, so it is the one used.

The run judged six claims:

- **The three reference claims,** each on every reading of its slot and compared with the frozen
  holds flags.
- **The three drift-reading statements,** each on its own drift reading (expected: holds) and on
  the true reading (expected: fails).

| | Result |
|---|---|
| Expected labels | 20 |
| Mismatches | 0 |
| Calls re-sent | 0 |
| Splits | 0 |
| (claim, reading) pairs whose three valid calls do not all agree | 0 of 28 |
| Tokens | 13,368 input, 2,928 output (about $0.06 at Anthropic's list price) |

The records hold claims and reading statements that name tables and columns of
LiveSQLBench-Base-Lite, under CC BY-SA 4.0 (see the README's list for `results/`).
