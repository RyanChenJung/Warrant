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

_To do._

## Descriptive results

_To do._

## The blind audit

_To do._

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
