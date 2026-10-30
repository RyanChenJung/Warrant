# The write line's thin run: write-up (#54)

Status: draft, in progress (PR #163). Due 2026-11-09.

Every number below comes from a committed file: `results/thin/README.md`, `results/thin/summary.json`,
`results/thin/2026-10-24-66a86cb.jsonl` and `results/thin/audit/`. Where a number is not in
`summary.json`, the text names the file it comes from. Terms are defined where they first appear and
in [CONTEXT.md](../../CONTEXT.md).

## Summary

_To be written last, from the sections below._

## What was run

### The question

When an AI agent keeps notes about a database for later use, which notes may it write on its own, and
which should a person write? The write line compares two answers to this at the same cost. Both
answers let a person write the same number of notes; they differ in which ones. The data is real
(a public benchmark), but the problems in it were planted by us, so the true answer is known.

### The data and the three planted defects

The data is LiveSQLBench-Base-Lite, SQLite release, revision `0664a2f` (`freeze/write_line.yaml`,
`release:`); the run uses two of its databases, `crypto` (a crypto exchange) and `alien` (an
alien-signal observatory set). The data is synthetic (disclosure 7).

A **defect** is a deliberate, recorded change to a clean copy of a database that makes one statement
about it ("a claim") true. Each defect has a **reference claim**: the statement, in the words a
knowledgeable person would use, that the change made true. There are three defects, one for each of
three **claim kinds**. They were written down and frozen in `freeze/write_line.yaml` before any was
injected (ADR 0007), and injected on 2026-10-19 (`injections/9cfd501f2182-write_line.json`; every
audit of the injection passed):

| Defect | Claim kind | What was changed | Reference claim |
|---|---|---|---|
| `wallet-sum` | column formula | In `crypto`, `accountbalances.walletsum` was set to `availsum + frozensum + margsum` on all 1,000 rows. | "The wallet balance walletsum in accountbalances includes the margin balance: it is the available balance availsum plus the frozen balance frozensum plus the margin balance margsum." |
| `orders-cut` | coverage | In `crypto`, the 266 cancelled orders were removed from `orders` (999 to 733 rows). Their executions, fees and risk records were kept. | "The orders table only holds orders that were not cancelled. Cancelled orders are missing from it, but their executions, fees and risk records are still in orderexecutions, fees and riskandmargin." |
| `seeing-recode` | value meaning | In `alien`, `observatories.seeingprofile` was recoded from 'Excellent', 'Good' and 'Poor' to '1', '2' and '3' on 963 rows, with '1' the best. | "The seeing grades in observatories.seeingprofile run from '1', the best seeing, through '2', to '3', the worst." |

A **slot** is a claim kind together with one subject: here (column formula, `accountbalances.walletsum`),
(coverage, `orders`) and (value meaning, `observatories.seeingprofile`). A knowledge store holds at most
one claim per slot. A **reading** is one competing interpretation of what the data means for a claim.
Each slot has a frozen **reading set**: `wallet-sum` has 5 readings, `orders-cut` 7 and `seeing-recode`
2. Exactly one reading is the true one, which the defect makes true. For example, `orders-cut`'s true
reading is "the cancelled orders were cut", and two of its rivals are "the archived orders were cut" and
"the orders are in another system".

### The check battery, "settled", and the predicted outcomes

A **check battery** is a fixed set of automatic checks run on a database; here, the vendored Gloss
detectors (`freeze/write_line.yaml`, `global.battery`), frozen before any defect was injected. A claim
is **settled** under a battery when it holds in every reading that the battery cannot tell apart from
the true one. "Not settled" means only that this battery did not settle it.

Before any agent ran, the battery's output on each reading's database fixed a **predicted outcome**
for each slot, committed in `predictions/9cfd501f2182-write_line.json`:

| Slot | Predicted outcome | Meaning |
|---|---|---|
| `wallet-sum` | agent alone | the battery settles it, so the agent can write the claim |
| `orders-cut` | both | the battery shows that some rivals do not fit, but three rivals (the archived orders were cut, the orders are in another system, the references are mistyped) leave the data identical, so only a person can settle the claim; the agent's own claim is still expected to add something |
| `seeing-recode` | person only | no reading changes the data, so only a person can say which way the grades run |

"Agent alone", "both" and "person only" say which contribution is expected to be measurable; the
descriptive results define them.

### The allocation rules, k and matched asks

An **allocation rule** decides, for each slot, who writes the claim into the **knowledge store**, the set
of claims the agent is given when it answers questions. The run has five rules:

- **empty:** no claims.
- **all person:** the reference claim, written by a person, for every slot.
- **all agent:** the agent's own claim for every slot it wrote one on.
- **settlement rule:** the agent writes exactly the claims the battery settles, and a person writes the rest.
  Here only `wallet-sum` is settled, so a person writes two slots.
- **confidence rule:** the agent writes the claims it is most confident in, and a person writes its least
  confident ones. How confident the agent is comes from **claim-writing samples**: it writes its claims
  10 times for each database, and a slot ranks higher the more often its claim agrees with sample 1's;
  its own stated confidence only breaks ties.

**k** is the number of slots a person writes under the settlement rule: **k = 2**. The two rules are
compared at **matched asks**: the confidence rule also sends exactly k = 2 slots to a person. The
confirmatory test of the write line (hypothesis H3) asks whether, at the same k, the settlement rule
leads to fewer wrong answers than the confidence rule. The person is simulated: a person's claim for a
slot is the slot's reference claim.

Each rule that writes agent claims runs under two **prompt variants** (ADR 0012), which differ only in
their last instruction: `confident` (the primary variant) has the agent write every claim it would make,
with a stated confidence, and `abstain` (descriptive only) has it write nothing it would only be
guessing. With the three agent-writing rules under both variants, the run compares **eight rules**:
`empty`, `all_person`, and `all_agent`, `settlement` and `confidence`, each with an `_abstain` version.

The agent's claims are labelled by a **judge**, a separate model operation. It is not told which reading
is true. For each claim and each reading in the slot's reading set it says whether the claim holds,
fails or is not addressed there, in three calls; the label that at least two calls give stands. A **wrong write** is an
agent claim the judge labels as failing under the true reading.

### The run

| | |
|---|---|
| Model | `anthropic.claude-sonnet-5` on Amazon Bedrock, us-east-1 (the lead's account); effort high; `max_tokens` 64,000 (a departure from the freeze, disclosure 14) |
| Run id | `f0b8374e7ebd4db0bcf049a8f82f3362` |
| Code and configuration | `main` at `66a86cb`; `configs/write_line_thin.yaml` (SHA-256 `2bc1e9c6a0e2…`), frozen at the run's first model call (ADR 0011) |
| Start | 2026-10-24 22:36:23 UTC; no stop, no resume, and the first-pass pause did not trigger |
| First complete pass | finished 2026-10-25 01:35:08 UTC, before the 2026-11-16 date that decides the second freeze (ADR 0011) |
| Complete | 2026-10-25 02:31:37 UTC |

In order, the run did the following (`results/thin/README.md`, `results/judge_validation/`):

1. **Judge validation**, on 2026-10-21 before any claim was written: the judge labelled the 6 frozen
   statements (each reference claim and each drift-reading statement) and matched all 20 expected labels
   (0 mismatches, 0 calls re-sent, 0 splits, and its three calls agreed on all 28 pairs).
2. **Claim writing:** 40 calls (2 databases × 10 samples × 2 prompt variants).
3. **Judging:** the 40 claims on a slot, one judgement each (the judge made its three calls on each).
4. **Stores:** the 8 knowledge stores, one per rule.
5. **Answers:** 33 questions × 8 rules × 3 runs = **792 answers**. The first pass (run 0) is 264 answers;
   runs 1 and 2 follow it. A failed call is retried (up to two attempts) and then recorded as a failure instead of scored.

The 33 questions are 23 **probe questions** (9 on `orders-cut`, 6 on `wallet-sum`, 8 on `seeing-recode`),
whose correct answer depends on whether the slot's claim is known, and 10 **control questions** on
content no defect touches. Their design is described under "Question design". The results file holds
882 records: the start record, 40 claim-writing samples, 40 judgements, 8 stores, 792 answers and the
complete record.

## Question design

_To be added from @lin-jhe-yu's section (due 2026-11-04)._

## Confirmatory result

**The confirmatory test did not run: the rules coincide.** Under both prompt variants, the settlement
rule and the confidence rule composed identical knowledge stores at k = 2. The comparison between them
has no question to test, so the frozen result is the one the freeze prescribes
(`global.confirmatory_test.rules_coincide`): **"rules coincide; H3 not tested at write time"**. H3 is
the hypothesis that, at matched asks, the settlement rule leads to fewer wrong answers than the
confidence rule. This is reported as it is: it was not re-run under another seed.

"Rules coincide" means that no slot is filled from different sources by the two rules. The test compares
the rules on the probe questions of exactly those slots (the question set called Q\*), and Q\* is empty
here (`summary.json`: `confirmatory.slots` and `confirmatory.questions` are empty, `test` is null).

Who wrote each slot's claim under each rule (`results/thin/README.md`):

| Rule | `wallet-sum` | `orders-cut` | `seeing-recode` |
|---|---|---|---|
| empty | none | none | none |
| all_person | person | person | person |
| all_agent, all_agent_abstain | agent | agent | none |
| settlement, settlement_abstain | agent | person | person |
| confidence, confidence_abstain | agent | person | person |

Why they coincide. Both rules leave exactly one slot to the agent when k = 2 and there are three slots.
The settlement rule leaves it to the agent because the battery settles it; the confidence rule because
the agent is most confident about it. Here those are the same slot:

- **`wallet-sum`** is the slot the battery settles. All 10 claim-writing samples of each variant wrote a
  claim on it and agreed (agreement 1.0; mean stated confidence 0.917 under `confident`, 0.927 under
  `abstain`). It ranked most confident.
- **`orders-cut`**: all 10 samples of each variant wrote a claim on it, but the claims varied (agreement
  0.1111, which is 1 of 9 other samples, under `confident`; 0.4444, 4 of 9, under `abstain`). It ranked
  second.
- **`seeing-recode`**: no sample wrote a claim on it (0 of 20 samples), so it ranked least confident.
  The claim-writing prompt names no slot, so an agent that is not pointed at a column does not write
  about it.

The confidence ranking, least confident first, was `seeing-recode`, `orders-cut`, `wallet-sum` under
both variants (`summary.json`: `confirmatory.ranking`, `descriptive.variants.abstain.comparison.ranking`).
So the confidence rule asked a person about `seeing-recode` and `orders-cut`, exactly the settlement
rule's two slots.

**What this does and does not say.** It says nothing about whether the settlement rule beats the
confidence rule: there was no test. Their accuracy over the defect probes was 0.826
(settlement) and 0.812 (confidence) under `confident`, but their stores are identical, so that gap is run-to-run noise (see the
descriptive results). ADR 0011 foresaw this outcome: with three slots and k = 2, each rule leaves one
slot to the agent, so the two stores either coincide or swap one slot, and an agent that is not pointed
at a slot makes coinciding likely. A second freeze with more slots exists (#61): the first pass finished before
2026-11-16, which ADR 0011 set as the condition for authoring it. Its test is reported separately and
is not pooled with this one.

## Descriptive results

Everything in this section is descriptive: no test was pre-registered for it, and the intervals show how
uncertain the figures are, not whether a result is "significant". Numbers are from
`results/thin/summary.json` and `results/thin/README.md` unless the text names another file.

### Accuracy by rule

Each rule answered the 23 probe questions three times (69 answers). **Accuracy** is correct answers and
correct refusals over all answers except clarification requests and failed calls. A **wrong answer** is
a scored answer that is wrong or an over-refusal.

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

The settlement and confidence rules answered from identical stores, so the difference between them is
run-to-run noise. The same holds for each `_abstain` pair.

### What each claim kind contributes

The **agent's contribution** A, for a claim kind, is accuracy when the agent writes every claim minus
accuracy with the empty store. The **person's contribution** P is accuracy when a person writes every
claim minus accuracy when the agent writes every claim. Both are computed per question and then
averaged over the kind's probe questions. The **allocation outcome** is read from the two with a cutoff
of 0.25 fixed in advance (`global.outcome_rule`):

- **agent alone** if A is at least 0.25 and P is below it;
- **both** if both are at least 0.25;
- **person only** if A is below 0.25 and P is at least it;
- **no measurable contribution** otherwise, which agrees with no prediction.

"Near the cutoff" flags a figure whose 95% bootstrap interval, over questions, contains 0.25; the
outcome is still read from the point estimate. **H1** is the hypothesis that each claim kind's measured
outcome equals its predicted outcome.

| Variant | Kind (probes) | A | P | Outcome | Predicted |
|---|---|---|---|---|---|
| confident | coverage (9) | −0.11 [−0.33, 0] | 0.74 [0.44, 1] | person only | both |
| confident | column formula (6) | 0.17 [0, 0.5] | 0.06 [−0.44, 0.5] | no measurable contribution, near the cutoff | agent alone |
| confident | value meaning (8) | 0 | 0 | no measurable contribution | person only |
| abstain | coverage | 0 | 0.63 [0.33, 0.89] | person only | both |
| abstain | column formula | 0.28 [−0.11, 0.67] | −0.06 [−0.5, 0.33] | agent alone, near the cutoff | agent alone |
| abstain | value meaning | 0 | 0 | no measurable contribution | person only |

**H1 agrees on 0 of 3 kinds under `confident` and 1 of 3 under `abstain`** (column formula, agent alone).

- **Coverage.** A person's note raised accuracy by 0.74 [0.44, 1] on the questions about the orders,
  and the agent's own notes added nothing over the empty store (A = −0.11). The predicted outcome was
  both. The claim that stands for the agent in the stores is sample 1's. Under `confident`, the judge labelled
  it "not addressed" on all 7 readings, so it settles none of them, which is consistent with A being
  at or below 0 (`results/thin/2026-10-24-66a86cb.jsonl`, the judgement of sample 1 on `orders-cut`).
- **Column formula.** The agent's contribution was 0.17 under `confident` (no measurable contribution)
  and 0.28 under `abstain` (agent alone); both intervals contain the 0.25 cutoff. The person's
  contribution was close to 0 under both variants.
- **Value meaning.** The empty store answered all 24 value-meaning answers (8 probes, 3 runs) correctly,
  so no note could add anything: A and P are both 0 under both variants. No claim-writing sample wrote a
  claim on this slot (0 of 20), so the agent's stores held none. The predicted outcome was person only;
  the defect opened no gap for a note to fill. Disclosure 6 anticipated that the direction of an
  undirected grade is not known in advance.

### Wrong writes

A **wrong write** is an agent claim, written into a store, that the judge labels as failing under its
slot's true reading. The **wrong-writes curve** counts them at every k from 0 (the agent writes every
slot it wrote a claim on) to 3 (it writes none), with the confidence rule's ranking deciding which slots
go to a person. It is **0 wrong writes at every k under both variants**, and the settlement rule's point
(2 asks) is also 0. A claim is **incomplete**, not wrong, when the judge leaves it "not addressed" on
its true reading. Under `confident`, one claim was incomplete at k = 0 and k = 1 (the claim on the
coverage slot, which goes to a person from k = 2 on) and none at k = 2 and 3; under `abstain` none was
incomplete at any k (`summary.json`: `curve.points`). The judge split no true reading.

### Other descriptive figures

- **Flip rate: 0.3125.** The share of questions whose three runs did not all give the same response
  class under at least one rule.
- **Judge instability.** The judge's three calls did not all agree on 6 of 120 (claim, reading) pairs
  under `confident`, none of them on a true reading, and on 8 of 120 under `abstain`, one of them on a
  true reading, settled 2 to 1 (the pair counts are in `summary.json`; which readings are in
  `results/thin/README.md`, and the results file agrees). No call was re-sent.
- **All 792 answers, by response class** (the results file): 671 correct answers, 101 wrong answers, 10
  correct refusals, 3 over-refusals, 4 clarification requests and 3 failures.
- **Failures.** The 3 failures came after retries: cancelled-share under `empty`, runs 0 and 1, where the
  model asked for more than 8 tool calls; and cancelled-limit-orders under `settlement_abstain`, run 2,
  where the response was malformed. The 4 clarification requests were all under `all_agent`.
- **The wallet-sum per-question review.** @lin-jhe-yu checked, probe by probe, whether the correct
  answers on the column-formula slot read `walletsum` or reach the answer by summing the balance
  columns, since a probe that can be answered without the note cannot show what the note is worth.
  The result is in PR #160 (`results/thin/wallet_sum_review/`), which is not merged yet:
  [N of M correct wallet-sum answers read `walletsum`; K use `availsum + frozensum`, all on one probe;
  from #160 after it merges]. [What this means for the column-formula figures above, from #160.]

## The blind audit

The judge's labels decide what counts as a wrong write and which claims agree with each other, so they
need a check. The **blind audit** (#123) is that check: a teammate who did not design the defects
labels the agent's claims himself, without seeing the judge's labels and without being told which
reading is true, and the two sets of labels are compared. The audit measures agreement only. **The
judge's labels stand** whatever the audit finds.

**What was labelled.** Juan (auditor id `juan-de-haro`) labelled the 20 distinct `confident` claims the agent wrote on a
slot (10 on `wallet-sum` and 10 on `orders-cut`; none was written on `seeing-recode`). For each claim
he gave a label (holds, fails or not addressed) for each reading in the slot's reading set: 5 readings
for `wallet-sum` and 7 for `orders-cut`, so **120 (claim, reading) pairs**. The blank sheet is
`results/thin/audit/2026-10-24-sheet.csv`, his labels are `2026-10-24-sheet-filled.csv`, the key that maps
each item to its defect and readings stayed out of the repo until the labels were in
(`2026-10-24-key.json`), and `2026-10-24-audit.jsonl` holds one record per claim. He wrote the labels
without AI; the commit that adds them carries a Claude Code co-author line, which covers the commit and
the PR (#145). It took him about 4 hours.

**Agreement** (`results/thin/README.md`; the audit file and the results file give the same counts):

| | Agree |
|---|---|
| All pairs | 108 of 120 |
| `wallet-sum` | 50 of 50 |
| `orders-cut` | 58 of 70 |
| True readings | 20 of 20 |

**The 12 differences**

- **Judge "fails", auditor "not addressed" (8).**
  - 7 are on one reading of `orders-cut`: "Cancelled orders were removed together with their executions,
    fees and risk records". The judge takes it to leave no orphan records, so a claim that counts
    orphans fails under it. The auditor takes it to say nothing about other orphans. His one
    practice-round difference was on the same reading.
  - 1 is on the "orders are in another system" reading, where the judge's three calls went 2 to 1.
- **Judge "fails", auditor "holds" (3).** On readings that keep the orders table complete: the "other
  system" reading (2) and the "mistyped references" reading (1). On one of them the judge's calls went
  2 to 1.
- **Judge "holds", auditor "fails" (1).** On the "archived orders" reading.

**How to read this.** The auditor and the judge agree on all 20 true readings and on every pair of
`wallet-sum`. The differences are on the rival readings of `orders-cut`, mostly on one reading whose
meaning the two read differently, so the judge's labels on those rivals are less certain than its labels
on the true readings. A wrong write is a claim that fails under the true reading, and the two agree on
every true reading, so the count of wrong writes (0) would be the same under the auditor's labels. The
confidence ranking uses the judge's whole profile of labels, so disagreements on rival readings could in
principle move it; this run's ranking is read from the judge's labels, as the freeze prescribes.

## Cost

_To do._

## Disclosures

_To do: disclosures 1 to 14, each with its latest wording (#54)._

## Limitations

_To do._

## What follows

_To do._

## How to reproduce

_To do._
