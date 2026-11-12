# The write line's second run (#153)

`2026-11-09-ab11a48.jsonl` holds the run's 761 records: the start record, 20 claim-writing samples,
59 judgements, 8 stores, 672 answers and the complete record. Every record carries the run's
provenance: repo commit `ab11a48`, the SHA-256 of `configs/write_line_second.yaml`
(`eb258e98ffb8425f8b34fc8271aed29afcd54c7cc38c7f5875da4a79373bf975`), the model
`anthropic.claude-sonnet-5` and the prompt version, 1. The run id is
`13df7df436aa434d9b82358eb1db221a`.

It was run on the lead's Bedrock account with the command in `docs/write-line-run.md` ("The second
run"), from `main` at `ab11a48`, after the judge's validation (#167) merged:

```bash
caffeinate -i uv run python -m warrant.write_line.run --config configs/write_line_second.yaml \
  --results results/second/2026-11-09-ab11a48.jsonl \
  --judge-validation results/judge_validation/2026-11-09-b88d33f.jsonl
```

- **Start:** 2026-11-10 00:06:10 UTC (2026-11-09 18:06:10 America/Chicago). It ran without a stop
  or a resume, under one run id.
- **The first-pass pause** did not trigger: the first pass's 224 answers cost $7.64, against an
  estimate of $8.75 and a pause above $17.50.
- **First complete pass:** finished 2026-11-10 02:07:22 UTC (2026-11-09 20:07:22 America/Chicago),
  before 2026-11-16 23:59 America/Chicago (#61).
- **Complete:** 2026-11-10 02:52:12 UTC (2026-11-09 20:52:12 America/Chicago).

## Other files

- `summary.json`: the summary (#154), recomputed from the results file with no model call:

  ```bash
  uv run python -m warrant.write_line.summary --config configs/write_line_second.yaml --results results/second/2026-11-09-ab11a48.jsonl --judge-validation results/judge_validation/2026-11-09-b88d33f.jsonl
  ```
- `audit/`: the blind audit (#155).
  - `2026-11-09-sheet.csv` is the blank sheet (#168).
  - `2026-11-09-sheet-filled.csv` is Juan's labels (#169).
  - `2026-11-09-key.json` maps each item to its defect, occurrences and readings. It stayed out of
    the repo until the labels were in.
  - `2026-11-09-audit.jsonl` holds one audit record per claim (30), written by:

    ```bash
    uv run python -m warrant.write_line.audit agreement --results results/second/2026-11-09-ab11a48.jsonl --sheet results/second/audit/2026-11-09-sheet-filled.csv --key results/second/audit/2026-11-09-key.json --auditor juan-de-haro --out results/second/audit/2026-11-09-audit.jsonl
    ```

## Confirmatory result: rules coincide

Under both prompt variants, the settlement rule and the confidence rule composed identical stores at
k = 2, so no test ran: "rules coincide; H3 not tested at write time" (`confirmatory.result`).

| Rule | exec-throttle | margin-cut | pnl-sign |
|---|---|---|---|
| empty | none | none | none |
| all_person | person | person | person |
| all_agent, all_agent_abstain | agent | agent | agent |
| settlement, settlement_abstain | agent | person | person |
| confidence, confidence_abstain | agent | person | person |

- **The confidence ranking**, least confident first, was margin-cut, pnl-sign, exec-throttle under
  both variants. Agreement alone set it: margin-cut 1/3 (`confident`) and 1/9 (`abstain`), pnl-sign
  7/9 in both, exec-throttle 1 in both.
- **Exec-throttle:** every sample restated the battery's finding, so it ranked most confident and
  kept the agent's claim, the risk `freeze/NOTE_2.md` names ("the formula slot may rank first
  again").

## The 59 judgements

Each of the 20 samples (10 per variant) could write one claim on each of the three defects' slots:

| Defect | Claim kind | Slot |
|---|---|---|
| exec-throttle | column formula | `systemmonitoring.exectimespan` |
| margin-cut | coverage | `users` |
| pnl-sign | value meaning | `accountbalances.realline` |

That is 60 possible judgements. `abstain` sample 7 wrote no value-meaning claim on
`accountbalances.realline` (its only claim on that column is a term-boundary claim), so there are 59. Every judgement is complete, with no error, no re-sent call and no split.

## Failures

25 of the 672 answers failed: 22 on a malformed response and 3 on the model asking for more than 8
tool calls. They are recorded as final and were not re-asked.

| Rule | Question | Failure | Runs |
|---|---|---|---|
| empty | snapshots-with-unstored-time | more than 8 tool calls | 0, 1, 2 |
| empty | margin-orders | malformed | 0 |
| all_person | margin-accounts | malformed | 1 |
| all_person | accounts-total | malformed | 2 |
| all_agent | margin-orders | malformed | 0, 1, 2 |
| all_agent | margin-accounts | malformed | 1, 2 |
| all_agent | margin-fees | malformed | 1, 2 |
| all_agent | margin-wallet-balance | malformed | 1 |
| all_agent_abstain | margin-fees | malformed | 0, 1, 2 |
| all_agent_abstain | margin-accounts | malformed | 0, 1 |
| all_agent_abstain | margin-orders | malformed | 0, 2 |
| all_agent_abstain | margin-wallet-balance | malformed | 1, 2 |
| all_agent_abstain | user-realised-pnl | malformed | 1 |
| confidence_abstain | margin-accounts | malformed | 1 |

- **By rule:** all_agent_abstain 10, all_agent 8, empty 4, all_person 2, confidence_abstain 1;
  settlement, confidence and settlement_abstain none.
- **By question:** margin-orders 6, margin-accounts 6, margin-fees 5, snapshots-with-unstored-time 3,
  margin-wallet-balance 3, user-realised-pnl 1, accounts-total 1.

The 672 answers also include 2 clarification requests.

## Cost

The recorded spend, the tokens at Anthropic's list price ($2 and $10 per million input and output
tokens). It is not compared with the Bedrock bill, which the lead cannot read (#54), so it is
unconfirmed.

| Step | Calls | Tokens (input, output) | Cost |
|---|---|---|---|
| Claim writing | 20 | 613,670, 312,580 | $4.35 |
| Judging | 59 judgements | 163,242, 296,821 | $3.29 |
| Answers | 672 | 10,011,879, 289,063 | $22.91 |
| The run | | | $30.56 |
| With the judge's validation (`results/judge_validation/2026-11-09-b88d33f.jsonl`) | | | $30.74, against the $80 cap |

The 25 failed answers account for $2.46 of the answers' cost.

## The blind audit (#155)

Juan labelled the 30 distinct `confident` claims on a slot, 160 (claim, reading) pairs, blind to the
judge's labels. The labels are his own; per #169, the only AI involvement was mechanical (checking
the file against the blank sheet, one stray space, the final line break, opening the PR).

| | Agree |
|---|---|
| All pairs | 135 of 160 |
| exec-throttle (column formula) | 65 of 70 |
| margin-cut (coverage) | 50 of 70 |
| pnl-sign (value meaning) | 20 of 20 |
| True readings | 27 of 30 |
| Without the one item with a note (C02) | 129 of 153 |

- **Judge `fails`, auditor `not_addressed` (10):** margin-cut's cut-with-children (9) and
  closed-accounts (1).
- **Judge `fails`, auditor `holds` (6):** margin-cut's other-system (3) and mistyped (2), and
  exec-throttle's as-released (1).
- **Judge `holds`, auditor `fails` (6):** margin-cut's other-system (3), and exec-throttle's
  throttle-wait (2, the true reading) and retry-rows (1).
- **Judge `holds`, auditor `not_addressed` (3):** margin-cut's closed-accounts (2) and
  exec-throttle's throttle-wait (1, the true reading).
- **The judge's three valid calls** did not all agree on 10 of the 160 pairs, 8 of them among the
  25 disagreements, all on margin-cut.
- **C02's note,** on retry-rows, the judge `holds` and auditor `fails` pair above: "The reading
  explains the extra amount reason".

The judge's labels stand; the audit measures agreement only.

The results are data derived from LiveSQLBench-Base-Lite (table and column names, values and SQL),
under CC BY-SA 4.0.
