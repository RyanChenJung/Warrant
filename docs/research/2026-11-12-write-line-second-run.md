# The write line's second run: write-up (#172)

Every number below comes from a committed file: `results/second/README.md`,
`results/second/summary.json`, `results/second/2026-11-09-ab11a48.jsonl`, `results/second/audit/`,
`configs/write_line_second.yaml`, `results/judge_validation/2026-11-09-b88d33f.jsonl`,
`freeze/write_line_2.yaml` and `freeze/NOTE_2.md`, or from the comments on #152 to #155. Where a
number is not in `summary.json` or the README, it was counted from the results file, and the text
says so. Terms are as in the first run's write-up
([`2026-10-30-write-line-thin-run.md`](2026-10-30-write-line-thin-run.md)) and `CONTEXT.md`; this
write-up defines only what is new. The second freeze is reported next to the first, not pooled
(`freeze/write_line_2.yaml`, line 3).

## Summary

**Why a second run.** In the first run the settlement rule and the confidence rule composed the same
stores, so H3 (at matched asks, the settlement rule leads to fewer wrong answers than the confidence
rule) was not tested. The second freeze (#61, #149) planted three new defects on `crypto`, chosen so
that the two rules could differ: a formula that holds on about 90% of rows, a coverage cut, and a
profit-and-loss sign that runs against the familiar convention ("Lever C", `freeze/NOTE_2.md`).

**What was run.** On 2026-11-09 (America/Chicago), Claude Sonnet 5 on Amazon Bedrock wrote claims
(20 samples), a judge labelled them (59 judgements), and the agent answered 28 questions (18 probes,
10 controls) under 8 rules, 3 times: **672 answers**, 25 of them failed calls. It cost **$30.56** at
list price ($30.74 with the judge's validation), not confirmed against the Bedrock bill.

**Result 1: the rules coincided again; H3 is not tested at write time.** Under both prompt variants
the two rules kept the agent's formula claim and asked a person about coverage and the sign. The
formula slot ranked most confident because every sample restated the battery's finding (agreement
1), the risk the freeze note named in advance ("the formula slot may rank first again"). As the
freeze fixes, this is reported as it is, and no third freeze is added (`freeze/NOTE_2.md`, line 42).

**Result 2: what each claim kind contributes (descriptive).** The predictions held for 2 of 3 kinds
under each variant:

- **value meaning (the sign):** a person's claim raised accuracy by 1.0, the agent's claim added
  nothing (predicted: a person only). Every one of the 20 claim-writing samples said somewhere that a
  positive value is a gain; none said the opposite.
- **column formula:** the agent's contribution was 0.4, near the cutoff (predicted: the agent alone),
  resting on two of six questions.
- **coverage:** not as predicted (predicted: both), mostly for reasons of measurement (see "What the
  run shows about the design").

**A descriptive finding on the sign.** On the one slot where the data cannot show the truth, the
agent was wrong in the same way every time, and none of its own signals marked the error clearly:
the wrong claim agreed with itself, under `confident` its stated confidence was about the same as when
the same claim was right in the first run, and the "don't guess" prompt did not hold it back. The wrong claim also
made wrong answers more confident. The person's claim fixed all 90 sign answers.

**The blind audit.** Juan labelled 160 (claim, reading) pairs blind to the judge's labels and agreed
with the judge on 135, including all 20 sign pairs.

**What it means.** As in the first run, there is no confirmatory result, so nothing here says which
rule is better. The run shows that the case the design aimed at exists in this setting: knowledge the
data cannot settle, on which the agent is consistently wrong. It does not show that the case is
common (`freeze/NOTE_2.md`, line 94).

## What was run

### What changed from the first run

| | First run (#54) | Second run |
|---|---|---|
| Freeze | `freeze/write_line.yaml` | `freeze/write_line_2.yaml`, `freeze/NOTE_2.md` (#149) |
| Databases | `crypto`, `alien` | `crypto` only |
| Slots | wallet-sum, orders-cut, seeing-recode | exec-throttle, margin-cut, pnl-sign |
| Questions | 23 probes, 10 controls | 18 probes, 10 controls |
| Claim-writing samples | 40 (2 databases × 10 × 2 variants) | 20 (10 × 2 variants) |
| Answers | 792 | 672 |
| Rules, variants, k, runs | 8 rules, 2 variants, k = 2, 3 runs | the same |
| Model block | Claude Sonnet 5, `max_tokens` 64,000 | the same |

### The three planted defects

| Defect | Claim kind, slot | What was changed | Reference claim |
|---|---|---|---|
| `exec-throttle` | column formula, `systemmonitoring.exectimespan` | `exectimespan` set to `apilatmark + queueline`, plus `10 * (110 - rateremain)` on snapshots where `rateremain <= 100` | "The execution time exectimespan in systemmonitoring is the API latency apilatmark plus the queue length queueline, except on some snapshots, where it also carries an extra amount that is not stored in any column." |
| `margin-cut` | coverage, `users` | the margin accounts (`acctscope = 'Margin'`) deleted from `users`; their balances and orders kept | "The users table only holds spot, futures and options accounts. The margin accounts, acctscope 'Margin', were left out of this export, but their balances and orders are still in accountbalances and orders." |
| `pnl-sign` | value meaning, `accountbalances.realline` | `realline` and `unrealline` negated | "The realised profit and loss realline in accountbalances is signed from the exchange's side: a positive value is a realised loss for the account holder and a negative value is a realised profit." |

Reading sets (`freeze/write_line_2.yaml`): `exec-throttle` has 7 readings (true: `throttle-wait`),
`margin-cut` 7 (true: `margin-left-out`), `pnl-sign` 2 (true: `positive-is-loss`; rival:
`positive-is-profit`). The predicted outcomes (`predictions/364d1ad381bb-write_line_2.json`) were
agent alone, both and person only. For `pnl-sign`, the battery's output is identical under both
readings (`bridge.pnl-sign.battery_tells_apart` is false): the data cannot show which way the sign
runs.

### The run

| | |
|---|---|
| Model | `anthropic.claude-sonnet-5` on Amazon Bedrock (the lead's account), prompt version 1 |
| Run id | `13df7df436aa434d9b82358eb1db221a` |
| Code and configuration | `main` at `ab11a48`; `configs/write_line_second.yaml` (SHA-256 `eb258e98ffb8…`) |
| Start | 2026-11-10 00:06:10 UTC (2026-11-09 18:06 America/Chicago); no stop, no resume |
| First pass | 224 answers, $7.64, against an estimate of $8.75 and a pause above $17.50, so no pause |
| Complete | 2026-11-10 02:52:12 UTC (20:52 America/Chicago) |

In order (`results/second/README.md`):

1. **Judge validation** (#167): 22 expected labels, 0 mismatches, 0 re-sent calls, 0 splits; 3 of
   32 (claim, reading) pairs decided 2 to 1.
2. **Claim writing:** 20 samples.
3. **Judging:** 59 judgements. `abstain` sample 7 wrote no value-meaning claim on `realline`; its
   only claim there is a term-boundary claim (positive meaning a realised gain). This is the
   kind of displacement disclosure 9 of the freeze note warned about for sample 1.
4. **Stores:** 8, one per rule.
5. **Answers:** 28 questions × 8 rules × 3 runs = 672. 25 failed after two attempts each (22 malformed
   responses, 3 with more than 8 tool calls) and 2 were clarification requests. Failed answers were
   recorded, not re-asked.

## Question design

The 28 questions are in `configs/write_line_second.yaml` (#152, PR #166, two review rounds). The
binding conditions of the freeze note ("Conditions on the questions") hold: the formula probes
separate only `as-released`, `retry-rows` and `sum-everywhere`, never a cause reading; coverage has
probes that separate `closed-accounts`, `other-system` and `mistyped`; no sign probe's gold joins
`users`. The `--check` gold answers and gaps are in the configuration's comments and `--check`.

| Set | Slot | Questions |
|---|---|---|
| Column formula | `exec-throttle` | 6: three on the unstored time (`snapshots-with-unstored-time`, `unstored-time-total`, `largest-unstored-time`) and three "all parts" probes (`total-time-all-parts`, `latency-share-all-parts`, `queueing-share-all-parts`) |
| Coverage | `margin-cut` | 6: `margin-accounts`, `accounts-total`, `spot-share`, `margin-orders`, `margin-wallet-balance`, `margin-fees` |
| Value meaning | `pnl-sign` | 6: `realised-loss-accounts`, `net-realised-pnl`, `total-realised-losses`, `profit-to-loss-ratio`, `large-realised-losses`, `user-realised-pnl` |
| Controls | none | 10, on market statistics and market data snapshots |

### What the run shows about the design

Each cell below is one rule's three runs: C correct, W wrong, O over-refusal, F failed, Q
clarification request (counted from the results file).

| Probe | empty | all_person | all_agent | settlement | confidence | all_agent_abstain | settlement_abstain | confidence_abstain |
|---|---|---|---|---|---|---|---|---|
| `snapshots-with-unstored-time` | FFF | CCC | CCC | CCC | CCC | CCC | CCC | CCC |
| `unstored-time-total` | OWO | CCC | CCC | CCC | CCC | CCC | CCC | CCC |
| `largest-unstored-time` | WWQ | CCC | CCC | CCC | CCC | CCC | CCC | CCC |
| `total-time-all-parts` | WWW | WWW | WWW | WWW | WWW | WWW | WWW | WWW |
| `latency-share-all-parts` | WWW | WWW | WWW | WWW | WWW | WWW | WWW | WWW |
| `queueing-share-all-parts` | WWW | WWW | WWW | WWW | WWW | WWW | WWW | WWW |
| `margin-accounts` | OWW | OFO | OFF | COO | CCC | FFO | OOC | CFO |
| `accounts-total` | WWW | OOF | WWW | CWC | CCC | CCC | WCC | COC |
| `spot-share` | WWW | WWW | WWW | WWC | WWW | WWW | WWW | WWW |
| `margin-orders` | FOO | CCC | FFF | CCC | CCC | FOF | CCC | CCC |
| `margin-wallet-balance` | OOW | CCC | OFQ | CCC | CCC | OFF | CCC | CCC |
| `margin-fees` | OOO | CCC | OFF | CCC | CCC | FFF | CCC | CCC |
| the six sign probes | WWW ×6 | CCC ×6 | WWW ×5, OOO | CCC ×6 | CCC ×6 | WWW ×5, WFW | CCC ×6 | CCC ×6 |

All 240 control answers were correct.

- **The three "all parts" probes were wrong under every rule, the person's included (72 of 72).**
  Every answer added the three columns (for example 2,080,490 against a gold of 1,069,195). The text
  ("counting API latency, queueing and execution time") reads as an instruction to add them, and no
  store's claim overrode it. The shape came from the lead's review of #166. They were fixed in
  advance, so they stay in the analysis, but they carry no contrast.
- **`spot-share` was wrong in 23 of 24 answers,** `all_person` included, so it carries no contrast
  either.
- **Over-refusals under the person's claim.** 10 answers under stores that hold the person's coverage
  claim refused on `margin-accounts` or `accounts-total`, reading "left out of the export" as "not
  countable", although the margin accounts' balance and order rows remain. Refusals are scored as
  errors.
- **Failures fall mostly on coverage under the agent's stores:** 17 of the 22 malformed responses are
  on coverage probes under `all_agent` and `all_agent_abstain`. A probe that fails in all three runs
  under a rule drops out of a contribution that needs that rule: `snapshots-with-unstored-time` drops
  out of the formula slot's A (empty failed), `margin-orders` (`confident`) and `margin-fees`
  (`abstain`) drop out of coverage's A.
- **The sign probes worked as designed.** Every one of the 50 wrong sign answers equals the rival
  reading's gold exactly. No sign answer equals a figure restricted to rows with a user, so the
  coverage cut did not leak into the sign slot (open risk 3 of the freeze note). The three
  over-refusals under `all_agent` on `user-realised-pnl` say no row exists for the user; the gold
  needs `TRIM` on a padded key, which is probably the cause.
- **Lesson for a later freeze:** a probe must not tell the answerer the operation the claim corrects,
  and a reference claim should say what remains and how to find it.

## Confirmatory result

**The confirmatory test did not run: the rules coincide.** Under both prompt variants, the
settlement rule and the confidence rule composed identical stores at k = 2, so the frozen result is
**"rules coincide; H3 not tested at write time"** (`summary.json`, `confirmatory.result`). The first
freeze's test stays primary, recorded as not run (`freeze/NOTE_2.md`, "The test"). With both freezes
coinciding, H3 is not estimated at write time in this study.

| Rule | `exec-throttle` | `margin-cut` | `pnl-sign` |
|---|---|---|---|
| empty | none | none | none |
| all_person | person | person | person |
| all_agent, all_agent_abstain | agent | agent | agent |
| settlement, settlement_abstain | agent | person | person |
| confidence, confidence_abstain | agent | person | person |

The confidence ranking, least confident first, was `margin-cut`, `pnl-sign`, `exec-throttle` under
both variants. Agreement alone set it (store records; mean stated confidence in brackets):

| Slot | `confident` | `abstain` |
|---|---|---|
| `exec-throttle` | 1 (0.73) | 1 (0.765) |
| `pnl-sign` | 7/9 (0.619) | 7/9 (0.675) |
| `margin-cut` | 1/3 (0.825) | 1/9 (0.85) |

**Why they coincide, across both freezes.** Both times, the slot whose claim restates a battery
finding had agreement 1 and ranked first, and it is the slot the settlement rule keeps. As frozen
(agreement first, stated confidence second), the confidence rule reproduces the settlement rule
whenever that holds. For the rules to differ here, the sign slot would have had to rank above the
formula slot. Even with 9/9 agreement it would have tied on agreement and lost on stated confidence
(0.62 against 0.73).

**What this does and does not say.** Over all defect probes the settlement rule's accuracy was 0.741
(14 wrong answers) and the confidence rule's 0.778 (12), but their stores are identical, so that gap
is run-to-run noise.

## Descriptive results

Everything here is descriptive: no test was pre-registered for it. Numbers are from
`results/second/summary.json` unless the text names another file.

### Accuracy by rule

Each rule answered the 18 probe questions three times (54 answers). Accuracy leaves out failed calls
and clarification requests.

| Rule | Accuracy | Wrong answers | Failure rate | Clarification rate |
|---|---|---|---|---|
| empty | 0.000 | 49 | 0.074 | 0.019 |
| all_person | 0.692 | 16 | 0.037 | 0 |
| all_agent | 0.200 | 36 | 0.148 | 0.019 |
| settlement | 0.741 | 14 | 0 | 0 |
| confidence | 0.778 | 12 | 0 | 0 |
| all_agent_abstain | 0.273 | 32 | 0.185 | 0 |
| settlement_abstain | 0.722 | 15 | 0 | 0 |
| confidence_abstain | 0.736 | 14 | 0.019 | 0 |

`all_person` is below 1 mainly because of the four probes that carry no contrast (the three "all
parts" probes, which no rule answered right, and `spot-share`, right once in 24) and its coverage over-refusals. Each settlement and confidence pair answered from
identical stores, so their differences are noise.

The freeze's sensitivity analyses on failures (failures as wrong, clarifications as wrong, all
defect probes) belong to the confirmatory test, which did not run; `summary.json` gives the all
defect probes figures above, and the failure and clarification rates per rule.

### What each claim kind contributes

A is the agent's contribution (all agent minus empty), P the person's (all person minus all agent),
read against the cutoff of 0.25; intervals are 95% bootstrap intervals over questions.

| Variant | Kind | A | P | Outcome | Predicted |
|---|---|---|---|---|---|
| confident | column formula | 0.4 [0, 0.8] | 0 | agent alone, near the cutoff | agent alone |
| confident | coverage | 0 | 0.4 [0, 0.8] | person only, near the cutoff | both |
| confident | value meaning | 0 | 1.0 | person only | person only |
| abstain | column formula | 0.4 [0, 0.8] | 0 | agent alone, near the cutoff | agent alone |
| abstain | coverage | 0.2 [0, 0.6] | 0.2 [−0.4, 0.8] | no measurable contribution, near the cutoff | both |
| abstain | value meaning | 0 | 1.0 | person only | person only |

**H1 agrees on 2 of 3 kinds under each variant** (column formula and value meaning). In the first
run it agreed on 0 of 3 and 1 of 3.

- **Value meaning.** No rule whose store lacked the person's sign claim answered a sign question
  right: 0 of 18 for the empty store and for the agent's store, and 0 of 17 scored for the abstain
  agent's store. Every rule whose store held the person's claim answered all 18 right (90 of 90).
  In the first run this slot gave no contrast, because the agent guessed the undirected grade right.
- **Column formula.** A = 0.4 rests on `unstored-time-total` and `largest-unstored-time`:
  `snapshots-with-unstored-time` dropped out (the empty store's three answers failed) and the three
  "all parts" probes carry no contrast. The agent's claim was as good as the person's here.
- **Coverage.** The agent's claims never named the margin accounts (0 of 20), so they could not help
  on the four margin probes; `spot-share`, one of the two probes a claim without the margin label
  could reach, was wrong under every rule. P's gains rest on single scored runs (each such probe has
  one scored agent answer, an over-refusal).

### The sign slot: claims, consistency and stated confidence

Counted from the results file:

- **Every sample said that a positive value is a gain.** Of the 19 claims on the sign slot (10
  `confident`, 9 `abstain`), 17 gave a direction, all "positive is a gain", and 2 gave none
  (`confident` samples 3 and 6, for example "the sign indicates gain versus loss"). Those 2 and
  `abstain` sample 7 said "positive is a gain" in another claim on the same column, so all 20
  samples said it somewhere. None said the opposite. The judge labelled 16 of the 19 wrong (8 per
  variant); it read one `abstain` claim ("both positive values (gains) and negative values (losses)
  occur") as not committing, and a near-twin of it as wrong.
- **The "don't guess" prompt did not hold it back.** Under `abstain`, 9 of 10 samples still wrote
  "positive is a gain" on the slot. In the first run, on the data as released, only 5 of 10
  `abstain` samples committed to a sign (disclosure 3 of the freeze note), so the prompt's effect
  is not stable across runs.
- **Consistency did not mark the error.** The wrong claim agreed in 7 of 9 later samples and so ranked
  as more reliable than the coverage claims (1/3 and 1/9), which all hold on their true reading. Under
  `confident` the two samples that differed named no direction; under `abstain` one wrote no claim
  and the other's direction was read as not committing. So no disagreement pointed to the right
  reading.
- **Stated confidence did not separate right from wrong, claim by claim.** The wrong sign claims were
  stated at 0.55 to 0.70 (mean 0.62) under `confident` and 0.55 to 0.75 (mean 0.68) under `abstain`.
  In the first run, where the same statement matched the release's documentation, `confident`
  samples stated it at 0.55 to 0.65 (mean 0.60). That comparison is across runs with different data
  and business-term lists. Compared across slots, though, the sign slot had the lowest mean stated
  confidence in both variants, so a ranking by stated confidence alone would have put it first for a
  person.
- **The wrong claim made wrong answers more confident.** The answers' stated confidence on the wrong
  sign answers rose from 0.733 under the empty store to 0.933 (`all_agent`) and 0.934
  (`all_agent_abstain`), above the 0.90 of `all_person`'s correct answers.
- **The person's claim won over the agent's.** Settlement and confidence stores also hold sample 1's
  claims outside the slots, one of which says positive values are realised gains. Under `confident`,
  their answers still followed the person's claim in 36 of 36 cases, at lower stated confidence
  (0.787 and 0.769) than `all_person`'s 0.90.

### The agreement split (#154)

The freeze note splits each slot's disagreement into the agent's part (a sample wrote no claim or a
different claim) and the judge's part (the judge's calls could have made the two claims agree)
("The agreement split").

| Variant | Slot | Agreement | Agent part | Judge part |
|---|---|---|---|---|
| confident | `exec-throttle` | 1 | 0 | 0 |
| confident | `margin-cut` | 1/3 | 2/9 | 4/9 |
| confident | `pnl-sign` | 7/9 | 2/9 | 0 |
| abstain | `exec-throttle` | 1 | 0 | 0 |
| abstain | `margin-cut` | 1/9 | 2/9 | 2/3 |
| abstain | `pnl-sign` | 7/9 | 2/9 (1 no claim) | 0 |

Most of coverage's disagreement is the judge's: the claims were close, and the judge's labels on
the provenance readings (`other-system`, `closed-accounts`) moved. So on coverage, agreement measured
the judge's instability as much as the agent's.

### Wrong writes and other figures

- **Wrong writes:** 1 at k = 0 and k = 1, 0 at k = 2 and 3, under both variants; the settlement rule's
  point (2 asks) is 0. The one wrong write is the sign claim, which goes to a person from k = 2 on.
- **Flip rate: 0.174,** 4 of the 23 questions with at least two scored runs under every rule.
- **Judge instability:** the three calls did not all agree on 10 of 160 pairs under `confident` and 9
  of 158 under `abstain`, none on a true reading. No call was re-sent.
- **All 672 answers, by response class:** 457 correct, 159 wrong, 29 over-refusals, 25 failed, 2
  clarification requests.

## The blind audit

Juan (`juan-de-haro`, #155) labelled the 30 distinct `confident` claims on a slot, 160 (claim,
reading) pairs, blind to the judge's labels. The key stayed out of the repo until his labels were in
(#169). The labels are his own; the only AI use was mechanical (#169). The judge's labels stand; the
audit measures agreement only.

| | First run | Second run |
|---|---|---|
| All pairs | 108 of 120 | 135 of 160 |
| Column formula | 50 of 50 | 65 of 70 |
| Coverage | 58 of 70 | 50 of 70 |
| Value meaning | none written | 20 of 20 |
| True readings | 20 of 20 | 27 of 30 |

- **The differences are mostly on coverage (20 of the 25), on its provenance readings,** as in the first run: judge fails
  and auditor not addressed on `cut-with-children` (9) and `closed-accounts` (1); and holds against
  fails on `other-system` both ways (3 each). On 8 of the 25 differences the judge's own three calls
  did not all agree.
- **The 3 true-reading differences are on the formula slot** (`C03`, `C07`, `C09`), all near-copies
  of `C01`, the sample-1 claim the stores use, which the auditor labelled as the judge did on every
  reading. So they reflect labelling of near-identical text, not a wrong claim on the settled slot.
- **The sign claims without a direction** (`C23`, `C26`) were labelled "holds" on both readings by
  both the judge and the auditor. The freeze note expected "not addressed" for such a claim (open
  risk 1, `freeze/judge_rubric.md`, lines 41-42).
- The auditor could read the first run's public key, so a learning effect is possible (disclosure
  13 of the freeze note).

## Cost

**The $30.56 is not confirmed by the Bedrock bill,** which the lead cannot read (#54). It is token
counts times Anthropic's list price ($2 and $10 per million input and output tokens).

| Step | Calls | Cost (list price) |
|---|---|---|
| Claim writing | 20 | $4.35 |
| Judging | 59 judgements | $3.29 |
| Answers | 672 | $22.91 |
| The run | | $30.56 |
| With the judge's validation | | $30.74, against the $80 cap |

The 25 failed answers account for $2.46.

**Method cost per rule** (`summary.json`, `descriptive.cost.method`), the cost of writing and judging
the claims a rule needs:

| | First run | Second run |
|---|---|---|
| settlement | $0.60 | $0.24 (one sample) |
| confidence | $6.31 | $3.76 (ten samples and their judging) |
| ratio | 10.5× | 15.9× |
| settlement_abstain / confidence_abstain | $0.42 / $6.13 (14.7×) | $0.21 / $3.89 (18.5×) |

Counting the answers, which both rules pay for, the confidence rule cost about twice as much in both
runs.

## Disclosures

The freeze note lists 14 disclosures (`freeze/NOTE_2.md`, "Disclosures"); they are not repeated
here. Where the run bears on them:

- **2, the formula slot may still rank first:** it did, and the rules coincided.
- **3, first-run statistics used to choose the slots:** the sign slot did what the first run
  suggested (the agent committed to the familiar sign), and more often under `abstain` than in the
  first run.
- **5 and 7, the sign contradicts the release documentation (KB 34):** the agents did not see it.
  Documentation was never offered to the claim writer, so the run does not test it, and here it
  would have said the opposite of the truth.
- **9, a term-boundary claim may take the value-meaning slot's place:** it happened in `abstain`
  sample 7, not in sample 1.
- **13, the auditor's possible learning effect:** see the blind audit.
- **14, aligned row keys:** the data suggests user rows were removed, which weighs against
  `mistyped` and `other-system`; no prediction uses it.
- **Open risk 3, an answerer may join users on the sign probes:** no sign answer was restricted to
  rows with a user.

Departures and other facts:

- The "all parts" probe shape came from the lead's review of #166, which also first suggested a
  latency share later pinned to the recorded latency (#166).
- The judge's validation was run once; one other invocation was a `--dry-run`, which calls no model
  (#153).
- 25 failed calls were recorded as failed and not re-asked, as the freeze fixes.

## Limitations

- **There is no confirmatory result in either freeze.** H3 was not tested; the per-rule accuracies
  are descriptive.
- **One database, three slots.** Each claim kind rests on one slot and six probes, and the formula
  and coverage figures rest on fewer: four probes carry no contrast, and failures removed others.
- **The sign case was built on purpose.** It shows what the agent does when such a convention holds,
  not how often such conventions occur in real data. Its realism rests on general knowledge rated
  "medium" (`freeze/NOTE_2.md`, "Realism case").
- **The person is the reference claim.** It shows that the right claim fixes the answers, not that a
  person would supply it.
- **One model.** Claims, judge and answers all use Claude Sonnet 5, and the defects were designed with
  an assistant of the same family.
- **One judge and one auditor,** who differ mostly on coverage's provenance readings.
- **The cost is not confirmed by the Bedrock bill.**

## What follows

- **No third freeze** (`freeze/NOTE_2.md`, line 42).
- **For later work, not this study:** a confidence ranking that does not put a battery-restating
  claim first by construction; probe wording that does not instruct the operation a claim corrects;
  reference claims that say what remains; a replication with another model family (#94).

## How to reproduce

The summary and the audit are recomputed from the committed files, with no model call. The run
itself is described in `docs/write-line-run.md` ("The second run").

```bash
uv run python -m warrant.write_line.summary \
  --config configs/write_line_second.yaml \
  --results results/second/2026-11-09-ab11a48.jsonl \
  --judge-validation results/judge_validation/2026-11-09-b88d33f.jsonl \
  --out <a new path>
```

```bash
uv run python -m warrant.write_line.audit agreement \
  --results results/second/2026-11-09-ab11a48.jsonl \
  --sheet results/second/audit/2026-11-09-sheet-filled.csv \
  --key results/second/audit/2026-11-09-key.json \
  --auditor juan-de-haro \
  --out <a new path>
```

Both give the committed files byte for byte.

The results are data derived from LiveSQLBench-Base-Lite (table and column names, values and SQL),
under CC BY-SA 4.0 ([LICENSE-DATA](../../LICENSE-DATA)).
