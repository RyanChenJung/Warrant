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

## The second run's validation (#153)

`2026-11-09-b88d33f.jsonl` holds the judge's validation for the second run, run before any of the
second run's claim-writing calls. The run refuses a validation made on another freeze (#147), so the
first file does not clear it. The file has 8 records: a start record, one record per validation
claim, and a completion record. Every record carries the run's provenance (repo commit `b88d33f`,
the SHA-256 of `configs/write_line_second.yaml`,
`eb258e98ffb8425f8b34fc8271aed29afcd54c7cc38c7f5875da4a79373bf975`, the model and the judge's prompt
version, 1) and run id `57c2e7644c714f49912c29acd7c0dd87`.

It was run on 2026-11-09 between 23:40 and 23:43 UTC with
`uv run python -m warrant.write_line.validate_judge --config configs/write_line_second.yaml --results results/judge_validation/2026-11-09-b88d33f.jsonl`,
from `main` at `b88d33f`. The judge was `anthropic.claude-sonnet-5` on Amazon Bedrock in us-east-1,
with the settings committed for claim writing: effort high, thinking at the model's default,
max_tokens 64000, and no sampling parameter. The rubric is `freeze/judge_rubric.md`, pinned to the
freeze commit. This is the second run's first complete validation run, so it is the one used.

The run judged six claims:

- **The three reference claims,** each on every reading of its slot and compared with the frozen
  holds flags.
- **The three drift-reading statements,** each on its own drift reading (expected: holds) and on
  the true reading (expected: fails).

| | Result |
|---|---|
| Expected labels | 22 |
| Mismatches | 0 |
| Calls re-sent | 0 |
| Splits | 0 |
| (claim, reading) pairs whose three valid calls do not all agree | 3 of 32 |
| Tokens | 16,011 input, 14,162 output (about $0.17 at Anthropic's list price) |

In each of the three pairs whose valid calls do not all agree, two of the three calls gave the
label the run kept. One of them has an expected label, which the kept label matches; the other two
are on readings with no expected label.

The records hold claims and reading statements that name tables and columns of
LiveSQLBench-Base-Lite, under CC BY-SA 4.0 (see the README's list for `results/`).
