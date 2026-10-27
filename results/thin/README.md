# The write line's full thin run (#54)

`2026-10-24-66a86cb.jsonl` holds the run's 882 records: the start record, 40 claim-writing samples,
40 judgements, 8 stores, 792 answers and the complete record. Every record carries the run's
provenance: repo commit `66a86cb`, the SHA-256 of `configs/write_line_thin.yaml` (`2bc1e9c6a0e2…`),
the model `anthropic.claude-sonnet-5` and the prompt version. The run id is
`f0b8374e7ebd4db0bcf049a8f82f3362`.

It was run on the lead's Bedrock account with the command in `docs/write-line-run.md`, from `main`
at `66a86cb`, after #122 (the questions) and #142 (the summary) merged.
- **Start:** 2026-10-24 22:36:23 UTC. It ran without a stop or a resume, and the first-pass pause
  did not trigger.
- **First complete pass:** finished 2026-10-25 01:35:08 UTC, before 2026-11-16, so the second
  freeze (#61) is authored (ADR 0011).
- **Complete:** 2026-10-25 02:31:37 UTC.

The run raised max_tokens to 64,000 and streamed every call before its first call (ADR 0013), a
disclosed departure from the freeze.

## Other files

- `summary.json`: the summary (#53), recomputed from the results file with no model call:

  ```bash
  uv run python -m warrant.write_line.summary --config configs/write_line_thin.yaml --results results/thin/2026-10-24-66a86cb.jsonl --judge-validation results/judge_validation/2026-10-21-4af7c61.jsonl
  ```
- `audit/`: the blind audit (#123).
  - `2026-10-24-sheet.csv` is the blank sheet (#144).
  - `2026-10-24-sheet-filled.csv` is Juan's labels (#145).
  - `2026-10-24-key.json` maps each item to its defect, occurrences and readings. It stayed out of
    the repo until the labels were in.
  - `2026-10-24-audit.jsonl` holds one audit record per claim, written by:

    ```bash
    uv run python -m warrant.write_line.audit agreement --results results/thin/2026-10-24-66a86cb.jsonl --sheet results/thin/audit/2026-10-24-sheet-filled.csv --key results/thin/audit/2026-10-24-key.json --auditor juan-de-haro --out results/thin/audit/2026-10-24-audit.jsonl
    ```

## Confirmatory result: rules coincide

Under both prompt variants, the settlement rule and the confidence rule composed identical stores at
k = 2, so no test ran: "rules coincide; H3 not tested at write time" (`global.confirmatory_test`).

| Rule | wallet-sum | orders-cut | seeing-recode |
|---|---|---|---|
| empty | none | none | none |
| all_person | person | person | person |
| all_agent, all_agent_abstain | agent | agent | none |
| settlement, settlement_abstain | agent | person | person |
| confidence, confidence_abstain | agent | person | person |

- **The confidence ranking**, least confident first, was seeing-recode, orders-cut, wallet-sum under
  both variants.
- **Seeing-recode:** no claim-writing sample wrote a claim on it (0 of 20), so it ranked least
  confident.
- **Wallet-sum:** all 10 samples of each variant wrote on it and agreed, so it ranked most confident.

## Descriptive results

Each rule answered the 23 defect probes three times (69 answers):

| Rule | Accuracy | Wrong answers |
|---|---|---|
| empty | 0.657 | 23 |
| all_person | 0.942 | 4 |
| all_agent | 0.631 | 24 |
| settlement | 0.826 | 12 |
| confidence | 0.812 | 13 |
| all_agent_abstain | 0.710 | 20 |
| settlement_abstain | 0.956 | 3 |
| confidence_abstain | 0.928 | 5 |

Settlement and confidence answered from identical stores, so their difference is run-to-run noise.

Contributions per claim kind (`global.outcome_rule`):
- A = accuracy(everything from the agent) − accuracy(empty store).
- P = accuracy(everything from a person) − accuracy(everything from the agent).
- The cutoff is 0.25. Intervals are 95% bootstrap intervals over questions.

| Variant | Kind | A | P | Outcome | Predicted |
|---|---|---|---|---|---|
| confident | coverage (9 probes) | −0.11 [−0.33, 0] | 0.74 [0.44, 1] | person only | both |
| confident | column formula (6) | 0.17 [0, 0.5] | 0.06 [−0.44, 0.5] | no measurable contribution, near the cutoff | agent alone |
| confident | value meaning (8) | 0 | 0 | no measurable contribution | person only |
| abstain | coverage | 0 | 0.63 [0.33, 0.89] | person only | both |
| abstain | column formula | 0.28 [−0.11, 0.67] | −0.06 [−0.5, 0.33] | agent alone, near the cutoff | agent alone |
| abstain | value meaning | 0 | 0 | no measurable contribution | person only |

- **H1:** the outcomes agree with the committed predictions on 0 of 3 kinds under `confident` and 1
  of 3 under `abstain`.
- **Value meaning:** the empty store answered all 24 value-meaning answers right, so no note could
  add anything.
- **Wrong writes:** none at any k, under either variant.
- **Flip rate:** 0.3125.
- **The judge's instability:** its three calls did not all agree on 6 of 120 (claim, reading) pairs
  under `confident`, none of them on a true reading, and on 8 of 120 under `abstain`, one of them on
  a true reading, settled 2 to 1. No true reading was split.
- **Failures:** 3 answers failed after retries:
  - cancelled-share under `empty`, runs 0 and 1: the model asked for more than 8 tool calls;
  - cancelled-limit-orders under `settlement_abstain`, run 2: a malformed response.

  The 792 answers also include 4 clarification requests.

## Cost

| Step | Calls | Cost |
|---|---|---|
| Claim writing | 40 | $9.70 |
| Judging | 40 judgements | $2.74 |
| Answers | 792 | $30.94 |
| The run | | $43.38 |
| With the judge's validation (`results/judge_validation/`) | | $43.43, against the $100 cap |

**Method cost per rule** (a call two rules need, sample 1, is in both):
- settlement: $0.60 and the battery's 5.3 seconds;
- confidence: $6.31, ten samples per database and their judging;
- under `abstain`: $0.42 and $6.13.

## The blind audit (#123)

Juan labelled the 20 distinct `confident` claims on a slot, 120 (claim, reading) pairs, blind to the
judge's labels. He wrote the labels without AI; the commit carries a Claude Code co-author line,
which covers the commit and the PR (#145). It took him about 4 hours.

| | Agree |
|---|---|
| All pairs | 108 of 120 |
| wallet-sum | 50 of 50 |
| orders-cut | 58 of 70 |
| True readings | 20 of 20 |

- **Judge `fails`, auditor `not_addressed` (8):**
  - 7 are on the reading "Cancelled orders were removed together with their executions, fees and
    risk records". The judge takes it to leave no orphan records, so a claim counting orphans fails.
    The auditor takes it to say nothing about other orphans. His one practice-round difference was
    on the same reading.
  - 1 is on the other-system reading, where the judge's three calls went 2 to 1.
- **Judge `fails`, auditor `holds` (3):** on the readings that keep the orders table complete: other
  system (2) and mistyped references (1). On one of them the judge's calls went 2 to 1.
- **Judge `holds`, auditor `fails` (1):** on the archived-orders reading.

The judge's labels stand; the audit measures agreement only.

The results are data derived from LiveSQLBench-Base-Lite (table and column names, values and SQL),
under CC BY-SA 4.0.
