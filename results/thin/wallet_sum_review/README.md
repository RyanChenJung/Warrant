# Wallet-sum per-question review (#54)

**Question** (asked on PR #122, 2026-10-24): under the true reading, walletsum = availsum +
frozensum + margsum. So an agent that sums the balance columns instead of reading `walletsum` can
reach the gold answer. For each wallet-sum probe, which answers read `walletsum`, and how many
correct answers rest on the components instead?

**Answer:**
- **Most correct answers read `walletsum`:** 102 of the 116 correct wallet-sum answers (88%).
- **14 (12%) use `availsum + frozensum` instead.** All 14 are on `user-wallet-excluding-margin`,
  where that sum equals the gold `walletsum - margsum`.
- **Every correct answer to the other five probes reads `walletsum`.**

## Method

The data is the 144 answers to the six probes with `defect: wallet-sum` in
`configs/write_line_thin.yaml`: 6 questions × 8 rules × 3 runs, from run
`f0b8374e7ebd4db0bcf049a8f82f3362` (`../2026-10-24-66a86cb.jsonl`).
- **Balance columns:** `walletsum`, plus the columns the wallet-sum readings in
  `freeze/write_line.yaml` compute it from: availsum, frozensum, margsum and unrealline.
- **Parsing:** each `final_sql` is parsed with sqlglot (SQLite dialect).
- **Deciding columns:** the balance columns in either of two places.
  - The answer expression: the outermost SELECT's one projection. If there are several, it is the
    one left after dropping bare column references. An alias is followed to its definition in a
    subquery or CTE.
  - Any WHERE, HAVING or JOIN condition in the query.

| Category | Rule | Answers |
|---|---|---|
| `reads_walletsum` | `walletsum` is among the deciding columns | 126 |
| `components_only` | no `walletsum`, at least one component | 17 |
| `unclear` | no single answer expression, no balance column, or SQL that does not parse | 0 (6 before the overrides) |
| `no_sql` | no final SQL | 1 (an over-refusal) |

**Manual overrides** (`manual_overrides.csv`): 3 distinct SQL strings, covering 6 answers, were
moved from `unclear` to `reads_walletsum` after a hand check. They are the `total-held` answers that
list `SUM(walletsum) AS total_wallet` and `SUM(margsum)`, and in five of them also their sum. Every
projection in them reads `walletsum`, and none of them has a route through the components alone.

## Results

Correct / wrong / other answers per question and category (`summary.csv`):

| Question | reads_walletsum | components_only | no_sql |
|---|---|---|---|
| total-held | 12 / 12 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| margin-majority | 24 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| frozen-majority | 24 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| available-majority | 24 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| user-wallet-excluding-margin | 4 / 2 / 0 | **14** / 3 / 0 | 0 / 0 / 1 |
| user-wallet-excluding-unrealised | 14 / 10 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

### `user-wallet-excluding-margin` per rule

The three empty-store answers all read `walletsum`. Seven rules have a wallet-sum note in their
store: the person's under `all_person`, and the agent's claim under the other six. Settlement and
confidence both leave wallet-sum to the agent (`../README.md`). Under those seven rules:
- 17 of the 21 answers use `availsum + frozensum`;
- 3 read `walletsum`;
- 1 has no SQL.

Answers per rule (A `reads_walletsum`, B `components_only`):

| Rule | Wallet-sum note in the store | A | B | No SQL |
|---|---|---|---|---|
| empty | none | 3 | 0 | 0 |
| all_person | the person's | 0 | 3 | 0 |
| all_agent | the agent's | 0 | 3 | 0 |
| settlement | the agent's | 0 | 3 | 0 |
| confidence | the agent's | 0 | 3 | 0 |
| all_agent_abstain | the agent's | 0 | 2 | 1 |
| settlement_abstain | the agent's | 2 | 1 | 0 |
| confidence_abstain | the agent's | 1 | 2 | 0 |

### Why it matters

- **The sum is the same under every reading.** Every reading in `freeze/write_line.yaml` changes
  only `walletsum`, and `without-margin` changes nothing. So `availsum + frozensum` has the same
  value whichever reading of `walletsum` holds, and it is the gold value.
- **So these answers do not test the note.** An answer that uses the sum scores the same whatever
  the note says `walletsum` is, so it cannot tell a correct note from a wrong one.
- **On this probe, most answers with a note did not test its content.**
- **No score is wrong because of it.** Every wallet-sum note in this run was correct. But the
  probe's correct answers under these seven rules are not evidence about the note.
- **A possible explanation, not a finding.** Both notes state `walletsum`'s formula. The agent's
  claim says "walletsum equals availsum + frozensum + margsum for all 1,000 rows". That may be why
  the agent switched to the components, but the records do not show its reasoning.

## The answer-column check

`answer_column_equals_gold` says whether the answer expression's column in the executed result
equals the gold value within the scoring tolerance (0.01). It is `undetermined` when there is no
single answer expression, and it does not change the category. It separates wrong answers that only
carry extra columns from wrong answers whose answer is wrong.

| Question | true | false | undetermined |
|---|---|---|---|
| total-held | 12 / 0 / 0 | 0 / 6 / 0 | 0 / 6 / 0 |
| margin-majority | 24 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| frozen-majority | 24 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| available-majority | 24 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| user-wallet-excluding-margin | 18 / 5 / 0 | 0 / 0 / 0 | 0 / 0 / 1 |
| user-wallet-excluding-unrealised | 14 / 0 / 0 | 0 / 10 / 0 | 0 / 0 / 0 |

(correct / wrong / other in each cell)

- **Every correct answer's answer column holds the gold value.**
- **5 wrong answers on `user-wallet-excluding-margin` hold the gold value in their answer column.**
  They were scored wrong only for their extra columns (`usertag`, or the balance columns listed
  beside the answer). Three are `components_only` and two `reads_walletsum`.
- **The 5 extra-column answers on `user-wallet-excluding-unrealised` are not near-misses.** Each
  lists `walletsum`, which is the gold value (528,690.97), but its answer column is
  `walletsum - unrealline` = 475,988.33. That is the value under the wrong readings `four-terms` and
  `with-unrealised-pnl`. The other 5 wrong answers to this probe return that value alone.
- **The 6 `false` answers on `total-held`** compute `SUM(walletsum) + SUM(margsum)`, the value under
  `without-margin`.
- **The 6 `undetermined` answers on `total-held`** are the overridden ones: they list several sums,
  so no single column is the answer.

## Limits

- **The components-only pattern rests on one probe and small counts.** It is on
  `user-wallet-excluding-margin` alone, against only 3 empty-store answers.
- **The records hold no reasoning.** They do not record why the agent chose its columns.
- **The review classes SQL text, not reasoning.** An answer that reads `walletsum` may still have
  been written with the formula in mind.
- **Aliases are resolved without scopes.** An alias defined twice would resolve to both of its
  definitions. No answer has one: the `note` column would say "alias defined more than once".
- **Any balance column in a WHERE, HAVING or JOIN condition counts,** including a guard such as
  `walletsum > 0`. In these answers, every such guard sits beside a comparison that already reads
  `walletsum`, so no category depends on it.
- **ORDER BY and LIMIT are not read.** No wallet-sum answer uses them to pick its value.
- **The 6 overridden answers are a hand judgment,** with its reason recorded in
  `manual_overrides.csv`.

## Files and how to re-run

- `answers.csv`: one row per answer.
- `summary.csv`: counts per question and category, per question, rule and category, and per question
  and answer-column value.
- `review_list.csv`: each distinct normalized SQL once, `unclear` first, then `components_only`,
  then `reads_walletsum`.
- `manual_overrides.csv`: the hand-checked categories.

The code is `warrant/write_line/wallet_sum_review.py`, with tests in
`tests/test_wallet_sum_review.py`. It rebuilds the injected copies in a temporary directory to read
the gold values, and calls no model:

```bash
uv run python -m warrant.write_line.wallet_sum_review --config configs/write_line_thin.yaml --freeze freeze/write_line.yaml --results results/thin/2026-10-24-66a86cb.jsonl --out-dir results/thin/wallet_sum_review
```
