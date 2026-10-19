# Freeze note: the write line (#34)

Reconstructed on 2026-10-14 from the session transcripts, the scratch files and the data directory,
read only, and completed before the commit. Times are UTC.

## What is frozen

- `freeze/write_line.yaml`: the global part and the three defects (column formula `wallet-sum` and
  coverage `orders-cut` in crypto, value meaning `seeing-recode` in alien), in #33's format.
- `freeze/judge_rubric.md`: the judge's prompt, frozen with the freeze (#34, decisions posted on
  2026-10-14). It was written from principles and not tried on any model; the lead read it on
  2026-10-14.

The clean databases are the release named under `release:` in the freeze file (revision and SHA-256).
This commit is pushed to the public repository before any defect is injected; GitHub's record of the
push is the evidence of order (ADR 0007 (d)).

## Checks before the commit

- `python -m warrant.freeze.validate --config freeze/write_line.yaml`, which finds the clean
  databases through the release configuration (#98): 0 errors, 0 warnings. The column formula's
  target and operands are numeric columns 2 to 5 of `accountbalances`, within the identity search's
  reach.
- Every transformation compiles against the release (`EXPLAIN` on a read-only connection), and every
  reference claim, reading statement and drift-reading claim passes the reference-claim check.
- Expected drift types: data-part drift for `wallet-sum` and `orders-cut`, convention drift for
  `seeing-recode`, as the maintenance line plans.
- Confounding clean-scan findings (#30): none under the reading of "touches" by the declared
  touches, so no defect was re-authored; read by table, `seeing-recode` would have seven (below).

### Confounding check against the clean scan

The source is #30's scan of the clean release at the fixed date 2026-10-12, with the
ordinal-direction probe (`docs/research/2026-10-13-clean-scan.md`, "Tables of the frozen defects",
and `docs/research/clean-scan.json`), and the rule is the frozen `confounding_rule`. No output of
the frozen battery on a database holding these defects exists before injection. The design trials
ran a stand-in battery on scratch copies holding `wallet-sum` and `orders-cut` (below), and its
output agrees with what follows; the recoding never went through any battery. So whether a finding
appears unchanged in the true reading's output was read off each true transformation and the scan's
counts, with read-only queries on the clean release. Unchanged means an identical record (table,
type, subject, statement, evidence), as the clean scan compares findings. A finding counts as on a
table if it was recorded while scanning that table.

| Defect | Findings on what it touches that bear on its claim kind | Unchanged under the true reading? |
|---|---|---|
| `wallet-sum` (`accountbalances.walletsum`, column formula) | RULE: walletsum equals availsum + frozensum on all 1,000 rows | No. Under `with-margin` the difference is margsum, at least 1,024.9 in absolute value on every row, against the identity search's tolerance of 0.005, so the search reports availsum + frozensum + margsum instead. |
| `orders-cut` (`orders`, whole table, coverage) | LINK: userlink joins to users for 100.0% of the 999 rows; LINK, recorded while scanning `orders`: 1 of 1,000 users is never referenced | No. The userlink finding changes in its count (100.0% of 733 rows), and the users finding goes from 1 to 267 of 1,000. |
| `seeing-recode` (`observatories.seeingprofile`, value meaning) | VALUE: seeingprofile holds Good (357), Excellent (315), Poor (291) | No. The recoding covers all 963 rows. |

The other findings on these tables bear on another claim kind, such as the GRAIN finding on
walletsum, and the VALUE code list on `orders.orderflow`, which maps to value meaning (agreed on
#34) and in any case loses Cancelled under the cut; or, for `seeing-recode`, they lie on columns it
does not touch. The three LINK findings recorded while scanning `fees`, `orderexecutions` and
`riskandmargin` name `orders` but are on tables the defect does not touch, and they change anyway:
266 of each table's 1,000 rows lose their order.

**How "touches" is read, and when.** The rule reads "a table or column the defect touches" by the
declared touches: a column-level defect touches its listed columns, and `orders-cut` touches its
whole table. Only `seeing-recode` depends on this. Read by table, it would be disqualified by seven
VALUE findings on other columns of `observatories`: `weathprofile` (2), `lunarstage` (2),
`solarstatus`, `geomagstatus` and `airtempc`, which bear on value meaning and which the recoding
leaves unchanged. `wallet-sum` and `orders-cut` pass under either reading. The lead adopted the
reading by declared touches, knowing the table-reading result, because the slot is a column: a
finding about another column cannot settle what seeingprofile's codes mean. The lead also knew what
the table reading would cost: on crypto and alien nearly every table with a code column has
value-meaning findings on other columns (the one candidate left was `users.acctscope`, an unordered
code list), so the value-meaning slot would have needed another database or been dropped, and the
freeze delayed. How the reading was settled, for readers who weigh it:

1. 2026-10-12 03:47: the design trials' stand-in scan of the alien copies already holds these seven
   findings.
2. 2026-10-12 04:18: the drafting notes, not public, review the candidate defects by "clean-scan
   findings on touched columns" and set findings "on untouched columns" aside; those were format
   findings on `accountbalances.unrealline` and `realline`, which bear on value meaning and so could
   not disqualify `wallet-sum` either way. For `seeing-recode` the notes list only "its code list"
   and do not mention the seven findings. They choose "a
   finding on a touched table or column, bearing on the defect's claim kind, that appears unchanged"
   over "any finding on a touched table", which they reject because it "would exclude
   accountbalances and orders entirely". Rejecting that option, which had no claim-kind or
   unchanged condition, does not settle table against column. The lead accepted the round, and
   round 1 was posted, at 17:26 and 17:27.
3. 2026-10-12 17:27: the rule posted on #34 (round 1) says "a table or column the defect touches",
   without saying which applies to a column-level defect.
4. 2026-10-13 17:17: the clean scan, with its section on the frozen defects' tables, is posted in
   PR #88 (announced on #34 at 17:21). The rescan with the probe, which changed no finding, followed
   on 2026-10-14 at 01:42.
5. 2026-10-14 05:37: a check of this draft reports that, read by table, the rule would disqualify
   `seeing-recode` through these seven findings.
6. 2026-10-14 05:39: the assistant adds the sentence reading "touches" by the declared touches to
   `confounding_rule` in the freeze file, with a second sentence naming the clean scan's claim-kind
   mapping, and reports the reading to the lead as settled by the drafting notes, not as a decision.
   The draft stays local.
7. 2026-10-17 22:14: the lead adopts the reading, knowing the table-reading result, after an account
   of items 1, 2, 5 and 6 that was later corrected. On 2026-10-18 at 00:46, given a corrected
   account, the lead confirms it, and on 2026-10-19 at 02:20, given item 2 as it stands above (the
   notes never applied the column reading to these seven findings), confirms it again. It is first
   public with the confounding record on #34 and with this commit.

## Settings decided at the commit

- **The judge's model** is written out: `anthropic.claude-sonnet-5` on Amazon Bedrock in
  `us-east-1`, the experiment model decided on #26 on 2026-10-14 at 04:16. The earlier text pointed
  to "the configuration's experiment model (#26)"; the configuration held a placeholder until PR #97
  merged at 18:47 that day.
- **Sampling.** Round 3 on #34 set the judge at temperature 0 and claim writing at a temperature
  above 0, and the draft followed it. Anthropic's Claude API reference as bundled with Claude Code,
  read on 2026-10-17 and 18 and not tried with a request, is inconsistent: one table lists sampling
  as removed for Claude Sonnet 5, while the migration guide says a non-default temperature, top_p or
  top_k is refused and a request that omits them is accepted. Either way the judge's temperature 0
  could not have been run, and the harness already sends none. So no sampling parameter is sent to
  the judge or for claim writing, and claim writing runs at the model's default, whose temperature
  is above 0, as round 3 asked. The migration guide also notes that temperature 0 never guaranteed
  identical outputs.
- **The judge's three calls** (decided by the lead on 2026-10-18, posted on #34). One call's labels
  are not guaranteed to repeat, so the judge calls three times per claim, in the same reading order,
  and each reading takes the label at least two valid calls give. A call that fails or does not
  label every reading validly is re-sent, at most three extra calls per claim, and the re-sent calls
  are reported. A reading on which the three calls give three different labels, or that has no label
  two valid calls share after the extra calls, is not_addressed: the judge does not settle the claim
  on it (the lead's reason: there an agent's claim should not be leaned on either, though no rule
  acts on that beyond the label). Splits are counted and reported. On the true reading a split makes
  an agent's claim incomplete instead of a wrong write, so a split never turns a claim into a wrong
  write, though splits on any reading can move the confidence ranking and with it which slots keep
  the agent's claim. True-reading splits of agent claims are reported separately, and the curve of
  wrong writes is also reported, descriptively, with the ranking unchanged and those splits counted
  as wrong writes when at least one valid call gives fails. This rule was chosen on 2026-10-18 when
  it was described to the lead as unbiased; after that was corrected the same day, the lead kept it
  and chose this disclosure and the descriptive curve.
  The combined labels are the judge's labels wherever they are used: agreement between claim-writing
  samples, wrong writes, the validation and the blind audit. The share of (claim, reading) pairs on
  which the three calls do not all agree is reported, for agent claims and validation claims
  separately; with one shared reading order it measures repeat instability, not order effects.
- **The validation's comparison** (2026-10-18): a holds flag of true expects holds and one of false
  expects fails; not_addressed, a split included, is a mismatch either way. The authors worded every
  reading whose flag is false to contradict the reference claim. For `filled-cut` the contradiction
  rests on reading "leaves out the filled orders" as leaving out only those, so a not_addressed
  there counts as a mismatch although the rubric's rule 2 could allow it.
- **The judge's runs and parsing** (2026-10-19): each claim is judged in one run, whose valid and
  re-sent calls are the only judge calls on it, and every answer is kept; a judge run repeated for
  any reason is reported with all its outputs, and the first complete run is the one used. Without a
  temperature, a repeated run could give other labels, so a rerun would otherwise let a result be
  chosen. A call's answer is the first JSON object in its text output, with labels matched exactly
  in lower case, so the parser is not chosen after the validation is seen.
- **Effort, thinking and max_tokens** (2026-10-18 and 19): the judge uses those fixed for claim
  writing, and they are fixed, committed and pushed to the public repository before the first model
  call on this freeze's defects or claims (the pilot, the judge's validation or claim writing,
  whichever comes first), so they are set before any output on them is seen. Round 3's deadline,
  "before the first real-model call", had already passed with the smoke test of 2026-10-14, which
  set neither, so it was replaced on 2026-10-19.

## Order of events

| When | What |
|---|---|
| 2026-10-11 16:45 | `CONTRIBUTING.md` states the rule: no defect is injected into any database before the freeze commit is pushed. It has no exception. |
| 2026-10-12 03:21 to 04:18 | A drafting workflow for #34 copies crypto and alien into a scratch directory, applies candidate defects to the copies and runs the Gloss detectors on them. |
| 2026-10-12 04:21 | The assistant tells the lead that these trials broke the letter of the rule. |
| 2026-10-12 17:27 | PR #84 adds the exception for disclosed trials on scratch copies, written after the trials, to cover them. |
| 2026-10-12 and 13 | The value-meaning defect changes from an Excellent/Poor swap to the 1/2/3 recoding (#26, #34); branch (b) of the drift-reading rule is amended for it on 2026-10-13. |
| 2026-10-13 17:17 | #30's clean scan of the release is posted in PR #88 (announced on #34 at 17:21). |
| 2026-10-14 04:13 to 18:45 | A teammate's smoke test calls the experiment model on the work-order fixture: said to be about to run at 04:13, reported at 18:45 and 18:50 ("Model calls"). |
| 2026-10-14 05:20 | The freeze file is first written. |
| 2026-10-14 05:20 to 05:36 | While this draft is checked, its statements are compiled and their effects previewed read-only on the release (below). |
| 2026-10-14 05:37 to 05:39 | A check reports the table reading's effect on `seeing-recode`; the reading by declared touches is added to the confounding rule (above). |
| 2026-10-14 05:51 | Last change to the freeze file before the edits of 2026-10-17 and 18. |
| 2026-10-17 | The draft is checked, read-only, against the code merged since (#88, #97, #98, #100), the confounding check is done, and the lead adopts the reading by declared touches (confirmed on 2026-10-18). |
| 2026-10-17 to 19 | The header, the judge's model, sampling, the judge's three calls, runs and parsing, the validation's comparison and the judge's other settings are changed (above), with the rubric's header comment to match, and `no_defect`, a mark the drift-reading rule no longer uses and on which the validator warned, is removed. |

## Design trials before the freeze

### What was tried

About 53 SQLite copies, all in the session's scratch directory, outside the data directory, and
about 100 battery runs.

| Claim kind | Candidate | Outcome |
|---|---|---|
| Column formula | `walletsum := ROUND(availsum + frozensum + margsum, 2)` | Frozen (true reading `with-margin`) |
| Column formula | the release's `walletsum = availsum + frozensum` | Reading `without-margin` (the clean table) |
| Column formula | `availsum + margsum`; `availsum + frozensum + unrealline`; `availsum + frozensum + margsum + unrealline` | Readings `without-frozen`, `with-unrealised-pnl`, `four-terms` |
| Column formula | `availsum + frozensum + realline`; `margsum := walletsum + unrealline`; `walletsum := availsum` | Dropped |
| Coverage | `DELETE FROM orders WHERE orderflow = 'Cancelled'`, child rows kept | Frozen (true reading `cancelled-cut`) |
| Coverage | the same cut with the child rows; the Filled orders cut | Readings `cut-with-children`, `filled-cut` |
| Coverage | the New and PartiallyFilled orders cut | Dropped |
| Value meaning | `seeingprofile` Excellent and Poor swapped | Replaced by the 1/2/3 recoding |
| Value meaning | `seeingprofile` recoded Excellent, Good, Poor to '1', '2', '3' | Frozen; never applied to a copy or run through any battery |

Besides these, copies checked that the injection order does not change the result and that a no-op
update changes the file bytes but not the content, and one copy applied the crypto defects with
foreign-key enforcement explicitly off.

### How they were run

- **Not the frozen battery.** The trials used the public Gloss release (b5025fb) with `run_all` per
  table, the ordinal-direction probe included, and stand-ins for what #28 and #30 later built: a CSV
  export read by DuckDB 1.5.5, and declared-key pairing patched into the link detector. Their results
  are provisional; the frozen battery is the vendored copy run by `warrant.battery.run` (#30).
- **Settings varied:** link pairing child to parent, both directions or names only; peers linked by
  a declared key or all tables; dates 2026-10-11, 2026-10-12 and 1999-01-01; normalisations exact,
  two significant figures, counts removed and code sets only.
- **Beyond the battery:** gold answers of candidate probe questions were computed by SQL on the
  defect copies (figures reused in #52), with content hashes, predicted outcomes and bridge
  predictions under each setting, and power calculations.

### What was chosen after seeing them

- The battery settings: exact normalisation, declared keys from child to parent only, peers linked
  by a declared key, the fixed date and positional floats in the export.
- That the clean database is not a value-meaning reading: on the swap copy its permuted code counts
  would have changed the prediction on counts that say nothing about meaning.
- The column-formula and coverage reading sets: every reading with a database of its own went
  through the battery before the sets were frozen, so how the battery partitions them was known.
- The confounding rule: the drafting notes chose it at the end of the trials, with each option
  described by its effect on the candidate defects. Its reading by declared touches was added on
  2026-10-14 and adopted on 2026-10-17 (see "Confounding check").

The safeguards: the drift-reading rule reads declarations only; the coverage defect's three
meaning-only readings are the answers the link check's own question offers, worded by the authors so
that the reference claim fails under them (#54, disclosure 10); and nothing here involved the
experiment model.

### Read-only contact with the data directory

While this draft was checked, its statements were compiled with `EXPLAIN` and their effects
previewed with `SELECT` queries on read-only connections to the clean release in the data directory.
Nothing was written: all 54 release files match `configs/livesqlbench-base-lite.sha256`, and none
changed after the fetch on 2026-10-11.

On 2026-10-17, while the draft was checked against the code merged since and the confounding check
was done, read-only queries on the clean release counted rows and checked values (for example the
Cancelled orders, margsum's zero or NULL values and the operands' decimal places), and the vendored
battery was run on a synthetic table of seeded random numbers, holding no release data, to see the
identity search find the three-term sum. Afterwards all 54 release files still matched the
checksums.

### Model calls

No project code called a model on any of these defects before this commit. The only configuration
project code runs against a model is the work-order fixture's, which holds none of them; the freeze
file names the judge's model but is read only by the validator, which calls no model; and on the
lead's machine the smoke command never ran and every write-line run used the scripted fake agent on
the work-order fixture.

On 2026-10-14 a teammate ran the experiment model through project code in the harness's smoke test
(#38): the question `open-orders` on the work-order fixture, a small database made up for the tests,
in one run under each rule (a run can make several model requests through its SQL tool). Its planted
defect `open-orders-cut` is not one of this freeze's defects and holds no release data, but it is a
coverage defect of the same shape as `orders-cut`. Under `empty` the answer was 0 (wrong), under
`all_person` 4 (right). The run's own time is not recorded: the teammate said at 04:13, in a message
to the lead, that they were about to run it (the model decision on #26 at 04:16 says "starting with
the #38 smoke run"), and reported the result in PR #97 at 18:45 and on #38 at 18:50. The defects'
transformations, reading sets and reference claims were all written before 04:13: `seeing-recode` as
posted on #34 on 2026-10-13, `wallet-sum` and `orders-cut` in the drafting notes of 2026-10-12,
partly posted on #34. This freeze file was first written at 05:20 that day, possibly after the run.
Its edits that day wrote out rules already decided; added to the confounding rule the reading of
"touches" by the declared touches (not a decision until 2026-10-17, see "Confounding check") and the
clean scan's claim-kind mapping; added procedures the assistant proposed as defaults (the judge's
reading-order draw and the seeded permutation of slots); added the rubric; narrowed the judge's
validation of drift-reading statements to two readings (posted on #34 at 05:55); and added declared
fields. None changed a defect's transformation, readings or reference claim.

The defects, the trials, the checks and the judge's rubric of this freeze were written with an AI
coding assistant, Claude Code running Claude Opus 5.5, of the same model family as the experiment
model (Claude Sonnet 5 on Amazon Bedrock, #26). The assistant's conversations are not available to
the experiment model. The rule "no model call touches a defect before the freeze commit is pushed"
refers to the experiment model, called through project code. A replication with a model from
another family, OpenAI's GPT, is future work (#94).

### Before the project's rules

On 2026-10-08, before this repository's rules existed, defect ideas were dry-run inside rolled-back
transactions on BIRD-Interact's PostgreSQL copies of cybermarket, mental and vaccine, and on a copy
of BIRD's beer_factory. None of these databases is used in the study.

## Corrections to earlier statements

Posted on #34 on 2026-10-14, with #54's disclosures 1 and 11 updated to match:

- #34, round 1 (2026-10-12): margsum's never being 0 and its 48 percent share came from read-only
  queries on the release, not from a scratch copy; the identity-search facts came from scratch copies.
- #34, amendment (2026-10-13): "the battery reports a few more findings on `observatories`" under the
  1/2/3 recoding was expected, not observed; the recoding was never run through a battery. The
  prediction does not depend on it, because both value-meaning readings share one database.
- #54, disclosure 1: the trials were wider than "candidate defects were tried on scratch copies";
  this note lists them.

Posted on #34 before the freeze commit:

- #34, corrections of 2026-10-14, item 3: "The experiment model was never called" holds for the
  defects and the design trials only. A teammate called it through project code on 2026-10-14 in
  #38's smoke test on the work-order fixture, at a time not recorded, possibly before that comment;
  no defect of this freeze was involved ("Model calls").

## Injection after the commit

`CONTRIBUTING.md` says the injection command refuses to run before the freeze commit is pushed. That
command and its guard are built in #36 (PR #99, open at this commit), and nothing is injected until
it is merged with the guard checking that the freeze file itself is committed (the review on #99).
Before the first injection the builder also refuses on a release revision or template SHA-256 that
differs from the freeze's (#36). The order set on #36, the builder author's plan with the lead's
additions of 2026-10-17: merge the freeze PR, pull main, run the command from main, then open a PR
with only the injection record (in `injections/`) and merge it as soon as CI passes, with no change
under `freeze/` or `warrant/battery/` in between. A reader checks order by finding that this commit
reached GitHub before the first commit that records an injection (ADR 0007).
