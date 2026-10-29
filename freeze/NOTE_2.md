# Freeze note: the write line, second freeze (#149)

Drafted on 2026-10-28, before any battery trial and before any model call on this freeze's defects or claims. Times are UTC.

## What is frozen

- `freeze/write_line_2.yaml` holds the second freeze of the write line. It is stage 1 of #61 under ADR 0011.
  - Its `release:` and `global:` parts are copied from `freeze/write_line.yaml`, unchanged except `claim_writing.grounding`, which names this freeze's business term, "realised profit and loss", pointing to `accountbalances.realline`, where the first freeze's named "wallet balance". The sampling text still lists "the pilot" among possible first model calls; this freeze has no pilot, and the text is kept word for word.
  - It has three defects on crypto, in declared injection order: the column formula on `systemmonitoring.exectimespan`, the coverage cut on `users`, and the value meaning of `accountbalances.realline`.
- `freeze/judge_rubric.md` is the first freeze's rubric. It is unchanged and still applies.
- **Why this freeze exists.** ADR 0011 allows a second freeze only if the first complete pass of the full run finishes by 2026-11-16 23:59 America/Chicago.
  - The pass finished on 2026-10-25 at 01:35:08. That is the latest of the 264 run-0 answer records of run `f0b8374e7ebd4db0bcf049a8f82f3362` (`results/thin/2026-10-24-66a86cb.jsonl`).
- **The first freeze's result.** Under both prompt variants, the settlement rule and the confidence rule built identical stores at k = 2. So no test ran: "rules coincide; H3 not tested at write time" (`results/thin/README.md`).
  - The confidence ranking, least confident first, was seeing-recode, orders-cut, wallet-sum.
  - That test stays the primary confirmatory test, recorded as not run.

The design was decided by the lead from 2026-10-25 to 10-28 and posted on #61 (issuecomment-6483767945).

## Scope

- **Three new slots only.** They are the column formula, coverage and value meaning slots.
  - They are injected on fresh clean copies.
  - They have their own freeze, configuration, k, matched asks and run id.
  - They are reported next to the first freeze, not pooled with it.
- **Crypto only.** #54's disclosure 13 (aligned integer row keys in crypto) extends to this freeze.
- **Disjointness applies within this freeze.**
  - The three defects touch disjoint tables and columns.
  - Tables the first freeze used may be reused on the fresh copies, and each reuse is disclosed below.
- **Same rules and variants as the first run.** The eight rules, both prompt variants and `runs: 3` are kept. `confident` is primary and `abstain` stays descriptive.

## The test

- **Alpha stays 0.05, by a rule written after the first run.**
  - If the first freeze's test had run, each test would have been at 0.025.
  - It did not run, so this test is at 0.05.
  - Either way the family-wise error rate is at most 5%.
- **The first freeze's test stays primary**, recorded as not run.
- **If this freeze's rules also coincide,** that is reported as it is. No third freeze is added.

## Why the design is what it is

On three slots, the two rules differ only if the slot the agent is most confident about is not the one the battery settles.

- In the first run the agent was most confident on wallet-sum, the settled slot. Both rules kept it and asked a person about the other two.
- That is likely again for any 100% formula the battery reports, since the agent copies the finding.

**Lever B is infeasible.** Lever B would make coverage battery-settled (k = 1). It cannot be done without leaving out a reading the glossary itself names, and the reason is structural.

- Every coverage defect has a reading "the table is complete; those rows never existed".
  - That reading leaves the database identical.
  - It changes the gold answer of every probe that separates the true reading from the drift reading.
  - It is the glossary's own example of a provenance part, "why rows are missing" (`CONTEXT.md`, "Provenance part").
- If that reading is included with `holds: false`, coverage is predicted "both" (`warrant/write_line/predict.py`, `outcome`).
- Four candidates were checked read-only and none survived: crypto today-orders, crypto API executions, alien obsdate >= 2023 and alien obsdate < 2018.

**Lever C: a realistic case that is hard for the confidence rule.**

- The agent is unsure about harmless noise: a column formula that holds on about 90% of rows, with exceptions whose cause an outsider cannot see.
- The agent is confident about a familiar-looking convention that is wrong here: profit and loss signed from the exchange's side.
- With k = 2, the confidence rule keeps only its most confident slot.
  - If that is the value-meaning slot, ranked ahead of both the formula slot and the coverage slot, the confidence rule keeps its wrong value-meaning claim. It asks a person about the formula and coverage.
  - The settlement rule keeps the formula claim and asks about coverage and value meaning.
  - Whether this happens depends on the agent's own samples. That is what H3 compares.

**The realism case, stated before injection.** Both situations occur in real data.

- Totals often equal the sum of their parts except on some rows:
  - invoices with discounts or refunds;
  - processing times with retries or throttling;
  - migrated legacy rows.
- Profit and loss is sometimes signed from the house side rather than the client side.
- The formula's realism assumes that a queued task adds about 1 ms, since `queueline` is a count.
- The formula slot's reading set was chosen knowing that it lowers that slot's agreement.

**Four conditions:**

1. **The judge labels the formula slot's readings steadily.** They are worded for that, so a drop in agreement comes from the agent's samples, not from judge noise. This rests on wording until the judge's validation, the first model call, tests it.
2. **The realism case is stated before injection** (above), together with the fact that the reading set was chosen knowing it lowers agreement.
3. **The report splits each slot's disagreement** into the agent's part and the judge's part, from the recorded calls ("The agreement split" below). The split is written here before any model call.
4. **The limit, stated in the write-up:** this shows the case exists, not that it is common.

## The reading-set rule

Written on 2026-10-28, before any battery trial, for all three claim kinds:

> A meaning-only reading (one neither the battery nor the data can tell from the true reading) is `holds: true` if it changes no probe's gold answer, and `holds: false` if it changes at least one.

- **It agrees with the first freeze.** orders-cut's `other-system` reading changes the count of cancelled orders, so it is `holds: false` there.
- **Its cost, disclosed:** a slot's probes ask about values as recorded, not about the unknown cause.

**The validator's limit on branch-(b) slots.**

- On a slot with no world-fixed rival, the drift-reading rule's branch (b) needs exactly one meaning-only reading besides the true one. It counts `holds: true` readings too (`warrant/freeze/validate.py`, the `rivals` check in the drift-reading block).
- So on such a slot, the reading set is the true reading plus the drift reading.
- The other candidates are listed below with their class. They are frozen with the set. The glossary's "Reading set" entry is amended to match (second PR of #149).
- The limit applies only to the value-meaning slot.
  - The formula slot and the coverage slot each have a world-fixed no-defect reading, so they fall under branch (a).
  - Their meaning-only readings stay inside the set: the formula slot's cause readings with `holds: true`, the coverage slot's provenance readings with `holds: false`.
  - `freeze/write_line_2.yaml` passes the validator with these readings (0 errors, 0 warnings).

**Value-meaning candidates outside the set** (`pnl-sign`, `accountbalances.realline`; the probes fix the sign for the account holder):

| Candidate | Form | Changes a probe's gold? | Class | Where |
|---|---|---|---|---|
| positive is a profit (client side) | meaning-only, convention | yes, every probe | `holds: false` | in the set: the drift reading |
| realline is the exchange's own profit and loss on the account | meaning-only | no: every probe asks for the account holder's figure | `holds: true` | this note |
| positive is cash out of the account (a debit) | meaning-only | no | `holds: true` | this note |
| a unit or currency rival (quote against base currency) | meaning-only | no: probes ask for the stored amount | `holds: true` | this note |
| a period rival (lifetime against this period) | meaning-only, provenance | no | `holds: true` | this note |
| one convention per format class | meaning-only | yes | would be `holds: false` | left out: the only split is the sign, so it is not a coherent reading, and branch (b) would re-author a second `holds: false` meaning-only reading |
| the clean data as released, `transformation: []` | world-fixed | yes | `holds: false` | left out: "the clean database is not a value-meaning reading" (`freeze/NOTE.md`, design trials). Including it would move the drift reading to branch (a), predict "both", and #50's warrant rule would refuse a surviving convention rival (`warrant/write_line/warrants.py`) |

Leaving out the `holds: true` candidates changes no prediction. They neither change the battery output nor count as a surviving rival.

## The agreement split

This section defines the split before any model call. #154 computes it from the run's records alone.

**Inputs.**

- One run's records, the first complete run, for one prompt variant and one slot `d`. These are the records the confidence ranking reads (`warrant/write_line/confidence.py`).
- Sample `s`'s claim on `d` is its first claim whose kind and subject equal the slot's (`slot_claim_index`).
- Its judgement is the first complete judgement record for (variant, `d`, `s`, index).
- For each reading `r`, three things are read from a claim's judgement:
  - `L(r)`: the combined label (`labels`);
  - `V(r)`: the set of labels its valid calls give (`valid`);
  - whether `r` is among its `splits`.

**Per sample.** Each sample `s` from 2 to 10 is put in exactly one class:

- **N, no claim:** `s` has no claim on `d`, or its sample record is a failure.
- **A, agrees:** `L_s(r) = L_1(r)` on every reading. This is `confidence.py`'s agreement: same profile.
- Otherwise let `D_s` be the readings where `L_s(r) ≠ L_1(r)`. For each `r` in `D_s`:
  - **Judge-type:** `r` is a split on sample 1's claim or on `s`'s claim, or `V_1(r)` and `V_s(r)` share a label. In both cases some valid call on one claim gives a label that a call on the other claim could give, so the judge's own calls could have made the two claims agree on `r`.
  - **Agent-type:** neither claim is split on `r`, and the two sets of call labels share no label.
- **C, claim differs:** at least one reading in `D_s` is agent-type.
- **J, judge differs:** every reading in `D_s` is judge-type.

**Per slot.**

- agreement = |A| / 9, the same as `confidence.py`.
- agent part = (|N| + |C|) / 9, with N and C also reported separately.
- judge part = |J| / 9.
- agreement + agent part + judge part = 1.

**Per reading.** Over samples 2 to 10, count the agent-type and judge-type differences on each reading. This shows which readings carry the judge's part. Condition 1 expects the formula slot's judge part to be near 0.

**Edge cases.**

- **Sample 1 has no claim on the slot, or failed.** There is no agreement, and the slot ranks least confident. The split is not defined; it is reported as "sample 1 has no claim".
- **A sample with no claim on the slot** is class N, part of the agent's part, and reported separately.
- **A split.**
  - A reading no two valid calls agree on is `not_addressed` (`warrant/agent/judge.py`, `combine`).
  - A difference on that reading is always judge-type, even if the other claim is `not_addressed` without a split.
  - If both claims are `not_addressed` on it, there is no difference.
- **A re-sent call.**
  - Only valid calls enter `V`. Failed and unparseable answers never enter it.
  - If the extra calls ran out with fewer than three valid calls, `V` holds the valid calls present, and a reading no two of them share is a split (judge-type).
  - Re-sent calls are counted and reported as the freeze already requires. They do not change a class.
- **A judgement made without a call** (an identical claim string, within the variant).
  - Its labels are copied, and its calls are those of the judgement it copies.
  - A sample whose string equals sample 1's is class A.
- **An incomplete judgement** is not used. The ranking refuses the run (`confidence.py`), so the split is not computed either.
- **Variants.** The split is computed per variant. `confident` is primary.

**What it does not measure.**

- It splits observed disagreement only. Agreements that judge noise could have broken are not counted. The freeze's existing share of unstable (claim, reading) pairs covers those.
- Two claims that say the same thing, which the judge labels steadily but differently, count as the agent's part. The blind audit can show such cases.

**Worked example: orders-cut in the first run.** Computed from `results/thin/2026-10-24-66a86cb.jsonl`.

- All 10 samples of each variant have a claim on the slot. Each judgement has three valid calls, no re-sent call and no split.
- **`confident`:** agreement 1/9, agent part 8/9 (N 0, C 8), judge part 0.
  - Sample 1's claim is about user uniqueness. All three calls give `not_addressed` on all 7 readings. Sample 2's claim does the same, so it agrees.
  - Samples 3 to 10 address the cut. Their calls give only `holds` or `fails`, so every one of the 7 readings is an agent-type difference: 56 in all, 8 per reading.
  - Agreement 1/9 matches `results/thin/summary.json`.
- **`abstain`:** agreement 4/9 (samples 2, 4, 6 and 8), agent part 1/9 (N 0, C 1), judge part 4/9.
  - Sample 1's calls on `other-system` are fails, holds, holds (combined: holds).
  - Samples 3, 7, 9 and 10 differ only there, with combined fails. Their calls include fails, so they are judge-type: class J.
  - Sample 5 also differs on `cut-with-children`: all three of its calls give `not_addressed`, against fails in all three calls on sample 1's claim. That is agent-type, so sample 5 is class C. Its `other-system` difference is judge-type.
  - Per reading: `other-system` has 5 judge-type differences, `cut-with-children` has 1 agent-type difference.
  - So one unsteady reading on sample 1's claim gives the whole judge part.
- **wallet-sum,** for contrast: agreement 9/9 under both variants, so there is nothing to split.

## The three defects

### The column formula: `exec-throttle` (`systemmonitoring.exectimespan`)

**The realism case, stated before injection.** A trading client paces its calls to stay under the
exchange's rate limit. It keeps a margin of 100 requests. Below that margin it waits before each
call, ten milliseconds for each request by which the remaining requests fall short of 110: 110 ms
with 100 left, 1,100 ms with none left. The wait is inside the recorded execution time and is not
stored on its own. So the execution time is the API latency plus the queue time on most snapshots,
and carries an extra amount on the throttled ones. This is pacing with a safety margin, not a pure
token bucket, which waits only once the allowance is used up. The same pattern occurs elsewhere:
processing times that include retries or throttling, invoice totals that equal their parts except
where a discount applies, legacy rows written by an older system. The story is general industry
knowledge; it was not checked against a named exchange's documentation.

**The unit assumption.** In the release's column meanings, `queueline` counts queued tasks or orders,
`apilatmark` is an average API latency and `exectimespan` an execution time in ms or s. Adding a
count to a latency makes sense only if each queued task adds about 1 ms. The true reading states
this assumption, and it is disclosed here because a domain reader would notice it.

**The relation is injected,** as `wallet-sum`'s was. On the clean copy `exectimespan` equals
`apilatmark + queueline` on no row of 1,000, and exceeds it on 153. The injection also changes the
column's scale: its mean goes from 494.41 to 1,069.19 and its maximum from 999 to 2,807. After
injection the relation holds on 901 of 1,000 rows. On the other 99, the rows with `rateremain` at
most 100 (none has exactly 100), the extra amount runs from 110 to 1,100. The holds share, 90.1%,
is above the identity search's bar of 80%. Its tolerance of 0.005 is far below the smallest extra
amount, so the search reports `apilatmark + queueline` with 99 rows left over. This comes from
reading `rule.py`; no battery-only trial has checked it yet. `apilatmark` and `queueline` are
integers, so the relation holds exactly on the other rows.

**Why the reference claim does not name the throttled snapshots.** The battery's identity finding
gives only the row count, the rows the relation holds on and the rows below the sum. Its statement
says "the remaining 99" without saying which rows they are. The claim writer sees the schema, the
battery output and the business terms, and runs no SQL (`warrant/write_line/run.py:536-537`). So
nothing the battery reports says that the exceptions are the rows with low `rateremain`. Suppose the
reference claim named that subgroup. A world-fixed rival with the same extra amount on another 99
rows would then be a reading under which the claim fails. If the battery could not tell that rival
from the true reading, the slot would be predicted both, not agent alone (`predict.py`, `outcome`),
and k would change. A person who knows the throttling would name it. Leaving it out lowers what the
person's claim carries, and that choice is disclosed. The claim says "on some snapshots", with no count or ratio, as ADR 0003 asks of reference claims.

**The rival "same extra on other rows" is not a reading.** It changes the database, so it is
world-fixed, and the reading-set rule, which is about meaning-only readings, does not apply. The
reference claim holds under it as written, so its flag would be `holds: true`. Then the predicted
outcome stays agent alone whether or not the battery tells it apart, and the drift reading does not
change, since the drift-reading rule reads only the empty transformation. Adding it would change
nothing that is predicted and would need an arbitrary choice of the other 99 rows. A probe about
the throttled snapshots has another gold answer under it. World-fixed rivals' gold answers are not
used, so that does not matter.

**`retry-rows` holds.** Under it, 106 snapshots, those where at least one call in twenty failed,
carry the latency again plus 200 ms. That is about one in ten, and the amount is in no column, so
the reference claim holds. The battery tells it apart: the relation holds on 894 of 1,000 rows.
`formulaC` drafted it as holds false under a reference claim that named the subgroup; the claim
used here does not.

**The cause readings.** `cause-retries`, `cause-old-logger` and `cause-gateway` share the injected
copy. They give another cause for the same extra amount on the same snapshots. Under the reading-set
rule they are `holds: true`, because the probes ask about values as recorded. Questions for this slot
(#152) must not ask what the extra amount is, because such a question would change gold under these
readings. The validator allows several meaning-only readings beside world-fixed rivals; the limit of
one applies only without them (`warrant/freeze/validate.py:149-159`). So they are in the set rather
than listed here. Their wording ("it is not a wait for the rate limit") aims to make the judge label
an agent's guessed cause steadily. The judge's validation is the first test of that. This reading
set was chosen knowing it lowers this slot's agreement.

**Candidates listed, not in the set:** a data-entry error (the extra amount is a recording
inconsistency, not time). This is the battery's own third answer to its identity question, class
provenance, and under the reading-set rule it would be `holds: true`.

**Confounding check.** The clean scan finds no column-formula finding on `systemmonitoring` (`docs/research/2026-10-13-clean-scan.md:297`), so nothing in the clean data disqualifies this defect under the confounding rule.

**Controls.** The three first-run controls on `systemmonitoring` (`api-errors`, `api-error-rate`,
`websocket-disconnected`) are replaced, since this freeze touches the table.

**Read-only queries on the crypto clean copy** (`sqlite3`, `mode=ro`), run while writing this
defect. The queries that chose the candidate are listed in `formulaC.json` (`sql_run`, both sets).
1. `SELECT sql FROM sqlite_master WHERE name='systemmonitoring'`
2. `SELECT count(*), sum(apilatmark IS NULL), sum(queueline IS NULL), sum(rateremain IS NULL), sum(exectimespan IS NULL), sum(exectimespan=0), min(exectimespan), max(exectimespan), round(avg(exectimespan),2) FROM systemmonitoring`
3. (short form) `SELECT sum(rateremain<=100), sum(rateremain<100), sum(rateremain=100), min/max of rateremain, queueline, apilatmark, typeof(apilatmark), typeof(queueline), typeof(rateremain) FROM systemmonitoring`
4. (short form) `WITH h AS (SELECT *, apilatmark+queueline + CASE WHEN rateremain<=100 THEN 10*(110-rateremain) ELSE 0 END AS t FROM systemmonitoring) SELECT count(*), sum(t<>0), sum(abs(t-(apilatmark+queueline))<0.005), sum(t<(apilatmark+queueline)-0.005), sum(t>(apilatmark+queueline)+0.005), min(t), max(t), round(avg(t),2), min/max extra on rateremain<=100, sum(t-(apilatmark+queueline)), typeof(t), sum(t<0) FROM h`
5. `SELECT sum(abs(exectimespan-(apilatmark+queueline))<0.005), sum(exectimespan>apilatmark+queueline+0.005) FROM systemmonitoring`
6. The same as 4 for `t = apilatmark+queueline` (holds, zeros, range)
7. The same as 4 for the `retry-rows` transformation (`... CASE WHEN apierrtotal*20>=apireqtotal THEN apilatmark+200 ELSE 0 END`)
8. `SELECT count(*) FROM systemmonitoring WHERE rateremain<=100 AND apierrtotal*20>=apireqtotal`
9. `SELECT sum(apireqtotal=0), sum(apireqtotal IS NULL), sum(apierrtotal IS NULL) FROM systemmonitoring`
10. `EXPLAIN` on each of the three UPDATE statements

### The coverage defect: `margin-cut`

**The realism case.** A customer table that holds only some of a firm's product lines is common in
real exports. Margin lending is often run by a separate legal entity or on a separate ledger, so an
extract of the customer master for one business unit leaves those customers out. The balance and
order tables come from the trading ledger, which is exported in full, so their rows for the left-out
customers stay in, without a customer to join to. The reference claim, "this export holds spot,
futures and options accounts only", is what a person who made or received such an export would
state.

**Why it is predicted both.** The battery sees the unmatched rows: its link check reports that
`accountbalances.usertag` and `orders.userlink` no longer join to `users` for every row, and asks
why. It cannot say why. The three meaning-only readings follow the three answers its own question offers
(retired records, records from another system, data-entry errors): `closed-accounts`,
`other-system` and `mistyped`. Each says the exchange has no margin accounts, so the judge cannot
read it as the true story told another way. They leave the injected copy identical. The #61 comment
named the first one "left out of the export"; it is written as closed accounts instead, because
the true reading already says the margin accounts were left out of the export.
Under the reading-set rule each is `holds: false`, because each changes the gold answer of a natural
probe: "How many margin accounts does the exchange hold?" is 224 under the true reading and none
under each of the three. This follows the natural design: lever B, a coverage slot the battery
settles, was found infeasible (#61).

**The other world-fixed readings.** `nothing-cut` is the no-defect reading and the drift reading
under branch (a). `cut-with-children` removes the margin accounts with their balances, orders and
those orders' child rows. `options-cut` cuts the account type whose count is closest to the margin
accounts' (243 against 224). Each is expected to give a battery output different from the true
reading's; the battery-only trials below check this.

**Disclosure: unmatched rows in the value-meaning slot's table.** The cut leaves 224 of the 1,000
rows of `accountbalances` without their user. `accountbalances` holds the value-meaning slot
(`realline`), and that defect does not modify it in rows or keys; it only negates `realline` and
`unrealline`. So the battery's finding on `accountbalances` comes from the coverage defect, not
the value-meaning one. Any probe on `realline` that joins to `users` (for example by account type)
would mix the two slots; the value-meaning probes do not join to `users`. The controls avoid
`users`, `accountbalances`, `orders` and its child tables. The `cut-with-children` reading's
database also loses those 224 rows; it is a reading's database, not the injected copy, and the
value-meaning readings' databases are not affected.

**Read-only queries on the clean copy** (sqlite3, `mode=ro` URI, on a copy whose SHA-256 matches the
freeze's `release.sha256.crypto`), run while designing this defect on 2026-10-28:

1. `SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;`
2. `SELECT m.name, p.* FROM sqlite_master m, pragma_foreign_key_list(m.name) p WHERE m.type='table';`
3. `SELECT m.name, p.name, p.type, p.pk FROM sqlite_master m, pragma_table_info(m.name) p WHERE m.type='table' AND m.name IN ('users','accountbalances','orders');`
4. `SELECT m.name, p.name FROM sqlite_master m, pragma_table_info(m.name) p WHERE m.type='table' AND (p.name LIKE '%user%' OR p.name LIKE '%acct%');`
5. `SELECT COUNT(*), COUNT(DISTINCT userstamp), SUM(userstamp IS NULL) FROM users;` (1000, 1000, 0)
6. `SELECT acctscope, COUNT(*) FROM users GROUP BY acctscope ORDER BY 2 DESC;` (Spot 287, Futures 246, Options 243, Margin 224)
7. `SELECT SUM(acctscope IS NULL), SUM(acctscope = '') FROM users;` (0, 0)
8. `SELECT COUNT(*), SUM(usertag IS NULL), COUNT(DISTINCT usertag) FROM accountbalances;` (1000, 0, 1000)
9. `SELECT COUNT(*), SUM(userlink IS NULL), COUNT(DISTINCT userlink) FROM orders;` (999, 0, 999)
10. `SELECT COUNT(*) FROM accountbalances a WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.userstamp = a.usertag);` (0)
11. `SELECT COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.userstamp = o.userlink);` (0)
12. `SELECT COUNT(*) FROM accountbalances a WHERE a.usertag IN (SELECT userstamp FROM users WHERE acctscope = 'Margin');` (224), and the same with `COUNT(DISTINCT a.usertag)` (224)
13. `SELECT COUNT(*) FROM orders o WHERE o.userlink IN (SELECT userstamp FROM users WHERE acctscope = 'Margin');` (223), and the same with `COUNT(DISTINCT o.userlink)` (223)
14. `SELECT COUNT(*) FROM users u WHERE acctscope='Margin' AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.userlink=u.userstamp);` (1)
15. `SELECT COUNT(*) FROM users u WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.userlink=u.userstamp);` (1)
16. `SELECT acctscope, COUNT(*) FROM users u WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.userlink=u.userstamp) GROUP BY acctscope;` (Margin 1)
17. `SELECT COUNT(*) FROM users u WHERE NOT EXISTS (SELECT 1 FROM accountbalances a WHERE a.usertag=u.userstamp);` (0)
18. `SELECT COUNT(*) FROM orderexecutions WHERE ordersmark IN (SELECT recordvault FROM orders WHERE userlink IN (SELECT userstamp FROM users WHERE acctscope = 'Margin'));` (224), and the same for `fees.orderslink` (224) and `riskandmargin.ordervault` (224)
19. `SELECT COUNT(*), COUNT(DISTINCT recordvault), SUM(recordvault IS NULL) FROM orders;` (999, 999, 0)
20. `SELECT (SELECT COUNT(*) FROM orderexecutions),(SELECT COUNT(*) FROM fees),(SELECT COUNT(*) FROM riskandmargin);` (1000, 1000, 1000)
21. `SELECT COUNT(*) FROM orderexecutions e WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.recordvault = e.ordersmark);` (0)
22. `SELECT ordersmark, COUNT(*) FROM orderexecutions GROUP BY ordersmark HAVING COUNT(*) > 1;` (one order, OB102450, 2), and the same on `fees.orderslink` and `riskandmargin.ordervault`
23. `SELECT o.recordvault, u.acctscope FROM orders o JOIN users u ON u.userstamp=o.userlink WHERE o.recordvault IN (SELECT ordersmark FROM orderexecutions GROUP BY ordersmark HAVING COUNT(*) > 1);` (OB102450, Margin)
24. `SELECT COUNT(*) FROM orders o WHERE o.userlink IN (SELECT userstamp FROM users WHERE acctscope = 'Options');` (243), and the same on `accountbalances.usertag` (243)
25. `SELECT ROUND(100.0*776/1000,1), ROUND(100.0*776/999,1), 1000-224, 999-223;` (77.6, 77.7, 776, 776)
26. `EXPLAIN` of each transformation statement of `margin-cut`, `cut-with-children` and `options-cut`: all compile.

**Confounding check.** The clean scan has one coverage-bearing finding on `users`: the LINK
finding "1 of 1000 users.userstamp values are never referenced by orders.userlink"
(`docs/research/2026-10-13-clean-scan.md:181`). `users` is a touched table, so this finding
counts. The one unreferenced user is a margin user (query 16 above), so the finding is expected to
disappear from the true reading's output; a battery-only trial must confirm it.

### Value meaning: `pnl-sign` (`accountbalances.realline`)

The clean copy queried is `crypto_clean.sqlite`. Its SHA-256 is 49103c15…a5e1, which is `freeze/write_line.yaml:20`.

**Validator.**
- `_defect` on this block, run in memory from `.venv`: no error and no warning. Every reading statement also passes `reference_claim_problems`: no digit, no comparison symbol, no uppercase SQL word. So no threshold is declared.
- The true reading is world-fixed and owns the defect's transformation byte for byte (`validate.py:117`; repeated in `build.py:135-143`).
- No world-fixed rival exists, so branch (b) applies (`validate.py:149-159`):
  - The set has exactly one meaning-only reading besides the true one (`:150-155`).
  - It is the drift reading.
  - It has `holds: false` (`:137-138`).
  - It carries its own reference claim, which also passes the check (`:158-162`).
- `expected_drift_type: convention` is one of the drift types the builder computes (`:45`, `:245-246`).
- `_disjoint` (`:175-194`) against the formula slot (`systemmonitoring: [exectimespan]`) and the coverage slot (`users: ["*"]`, as drafted) finds nothing shared. The whole-freeze `validate` is still to be run on the finished file.

**Audit (`warrant/defects/audit.py:61-78`, `:92-110`).**
- `inject` takes a snapshot just before and just after each defect (`inject.py:59-63`). So this audit compares the copy after the formula and coverage defects with the copy after the negation.
- The audit refuses if any old value maps to two new values, or two old values to one, in any column of any table.
- realline and unrealline each have 1,000 distinct values, with no NULL and no 0, and their negations are 1,000 distinct each. So the recoding is one-to-one on both columns, and no row or other column changes.
- The users rows the coverage defect removed are already gone in both snapshots, so they do not enter this audit.
- Stored types (realline/unrealline): 975 rows real/real, 15 integer/real, 9 real/integer, 1 integer/integer. Negation keeps the type [inference from SQLite type affinity].
- `inject` was not run. Acceptance is shown by these counts, not executed.

**The true reading's database.**
- `build` builds it from the clean copy, the other defects' true transformations in declared order, then its own (`build.py:160-174`). It refuses if the result is not the injected copy.
- The negation only touches accountbalances, and the users delete only touches users, so the order changes nothing.
- Both readings are meaning-only or the true one, so both share the injected copy.

**Reading set, under the reading-set rule.**
- The rule (#61 design comment): a meaning-only reading is `holds: true` if it changes no probe's gold, and `holds: false` if it changes at least one.
- On this branch-(b) slot the validator allows only one meaning-only reading besides the true one. So the other candidates are listed here with their class, frozen with the set.

| Candidate | Form | Changes a probe's gold? | Class | In the set? |
|---|---|---|---|---|
| positive = profit (client side) | meaning-only, convention | yes, all six | `holds: false` | yes, the drift reading |
| realline is the exchange's own P&L on the account | meaning-only | no: every probe asks for the account holder's figure | `holds: true` | no, `validate.py:150-155` would refuse it |
| positive = cash out of the account (debit) | meaning-only | no | `holds: true` | no, same reason |
| unit or currency (quote against base currency) | meaning-only | no: probes ask the stored amount | `holds: true` | no, same reason |
| period (lifetime against this period) | meaning-only, provenance | no | `holds: true` | no, same reason |
| one convention per format class | meaning-only | yes | would be `holds: false` | no, see below |
| clean data as released, `transformation: []` | world-fixed | yes | `holds: false` | no, see below |

- **One convention per format class.** The VALUE finding's only split is the sign. So this reading makes every row a loss, or every row a profit, which is not a coherent reading. It would also be a second `holds: false` meaning-only reading, which branch (b) sends back for re-authoring.
- **Clean data as a world-fixed reading.** The first freeze ruled it out ("the clean database is not a value-meaning reading", `freeze/NOTE.md:209`). Here it would also break the pipeline:
  - The validator accepts it only with the drift reading moved to it. Left at `positive-is-profit`, it errors at `validate.py:142-148`.
  - Its battery output differs (the VALUE counts swap), so the slot would be predicted "both" (`predict.py:130-136`).
  - The convention rival still survives, so `warrants.py:89` refuses "predicted both with a surviving convention rival".
- **Leaving out the `holds: true` candidates changes no prediction.** Their output does not differ, but they hold, so none is a surviving rival (`warrants.py:63-64`).
- **A coverage-style reading cannot enter here.** A reading such as "the balance rows with no user are not accounts" is about the coverage slot, not about the sign. The probes below are worded so it changes no gold.

**Drift reading, prediction and warrant.**
- Branch (b): the drift reading is `positive-is-profit` (`freeze/write_line.yaml:62-63`). It shares the injected copy, so the drift type is convention (`:67-68`; `build.py:180-182`). The bridge prediction is that the battery does not tell it from the true reading.
- **Predicted: person only.** No reading's output differs, and the rival has `holds: false` (`predict.py:132-135`).
- **Warrant.** The surviving rival is a meaning-only convention reading on a person-only slot. So the agent's claim carries no warrant, and the person's claim a declaration warrant (`warrants.py:85-86`).

**Battery output, before and after.**
- **realline VALUE.**
  - Before (`docs/research/2026-10-13-clean-scan.md:132`): "dominant class is alphanumeric (example -10251.85, 511 rows); 489 rows … 10037.25".
  - After [inference, `value.py:186-215`]: "dominant class is numeric (example 10251.85, 511 rows); 489 rows use a different format, for example: -10037.25".
- **unrealline VALUE.**
  - Before (`clean-scan.md:131`): "numeric (example 10030.42, 513 rows); 487 … -10012.72".
  - After [inference]: "alphanumeric (example -10030.42, 513 rows); 487 … 10012.72".
- **How the after examples were found.** They are the minima of `CAST(-col AS TEXT)` per sign class. The same expression gives the clean examples exactly.
- **GRAIN** on both columns does not change: 1,000 distinct values.
- **RULE.** No sum of two or three numeric columns holds on any row with negated realline or unrealline, in 195 combinations (identity search in `scratchpad/vm61/idsearch.sql`). The walletsum RULE stays as released (`clean-scan.md:136`).
- **LINK on usertag changes because of the coverage defect, not this one.**
  - Before: "joins to users.userstamp for 100.0% of the 1,000 rows" (`clean-scan.md:115`, `:127`).
  - After the cut: 776 of 1,000 rows join [the finding's wording is inferred].
  - Both readings share the injected copy, so this changes no reading's output relative to another and no prediction.
- **Confounding rule** (`write_line.yaml:69-75`). Of the 12 clean-scan findings on accountbalances, only the two VALUE findings bear on value meaning, and both change. GRAIN and LINK map to other claim kinds (`warrant/data/clean_scan.py:51-59`). Nothing disqualifies the defect.
- A battery-only trial would confirm this wording, and it is listed here if run.

**What the coverage cut changes on this slot's table.** accountbalances is not modified by the cut, but its usertag references users, which loses its 224 `acctscope = 'Margin'` rows.
- In the clean copy, all 1,000 accountbalances rows join users (exact and trimmed). By scope: Spot 287, Futures 246, Options 243, Margin 224. After the cut, 224 balance rows have no user.
- The foreign key `accountbalances_usertag_fkey` has no delete action. `inject` opens SQLite without foreign-key enforcement (`inject.py:55`), so the delete goes through and the balance rows stay.
- **The readings are unaffected.** They say only how the sign is read. The recoding and the audit counts are as stated above.
- **The probes are affected through their population.** Asked about "account holders", an answerer could take the users table as the list of account holders and join it. On the injected copy that restricts the count to 776 rows and changes five of the six golds:

| Probe | Gold over all balance records (true / rival) | If restricted to rows with a user (true / rival) |
|---|---|---|
| realised-loss-accounts | 511 / 489 | 393 / 383 |
| net-realised-pnl | -1,547,338.14 / 1,547,338.14 | -320,617.86 / 320,617.86 |
| total-realised-losses | 26,051,086.46 / 24,503,748.32 | 19,533,303.68 / 19,212,685.82 |
| profit-to-loss-ratio | 0.9406 / 1.0631 | 0.9836 / 1.0167 |
| large-realised-losses | 465 / 442 | 353 / 345 |
| user-realised-pnl (U458616) | -99,813.64 / 99,813.64 | unchanged: U458616 is a Spot user and stays in users |

- **Why this matters.** Whether the answerer drops those rows could depend on the coverage claim in its store. A person's claim says the Margin accounts were left out of the users export. An agent's claim might call the unmatched rows errors. The value-meaning slot's A and P would then carry an effect of the coverage slot.
- **The gold over all balance records is right under every coverage reading:**
  - under the coverage true reading, the Margin accounts exist and only their user rows were left out;
  - under the coverage drift reading, every balance row has its user;
  - under the provenance readings, the rows are still balance records.
- **So the probes ask over balance records, not over account holders as a population.** The account holder stays named only as the side whose profit or loss is meant. The first freeze's wallet probes said "accounts", and its controls "… records".

**Probes** (the starting point for #152).
- Golds are computed on the clean copy, with `r = -realline` standing in for the injected value. Gold SQL is written in the injected copy's terms, and `separates:` holds the rival's SQL.
- **Changes from the accepted draft:**
  - "account holders" as a population becomes "account balance records";
  - "for the account holder" now fixes whose profit or loss is meant.

| id | Question | Gold, true | Rival (`positive-is-profit`) |
|---|---|---|---|
| realised-loss-accounts | How many account balance records show a realised loss for the account holder? | `SELECT COUNT(*) FROM accountbalances WHERE realline > 0` = 511 | `… WHERE realline < 0` = 489 |
| net-realised-pnl | What is the net realised profit and loss across all account balance records, positive meaning a net profit for the account holders? | `SELECT -SUM(realline) FROM accountbalances` = -1,547,338.14 | `SELECT SUM(realline) FROM accountbalances` = 1,547,338.14 |
| total-realised-losses | What is the account holders' total realised loss across all account balance records, as a positive amount? | `SELECT SUM(realline) FROM accountbalances WHERE realline > 0` = 26,051,086.46 | `SELECT -SUM(realline) FROM accountbalances WHERE realline < 0` = 24,503,748.32 |
| profit-to-loss-ratio | Across all account balance records, what is the ratio of the account holders' total realised profits to their total realised losses? | `SELECT -SUM(CASE WHEN realline < 0 THEN realline END) / SUM(CASE WHEN realline > 0 THEN realline END) FROM accountbalances` = 0.9406 | `SELECT SUM(CASE WHEN realline > 0 THEN realline END) / -SUM(CASE WHEN realline < 0 THEN realline END) FROM accountbalances` = 1.0631 (KB 34's formula as written) |
| large-realised-losses | How many account balance records show a realised loss above 10,000 for the account holder? | `SELECT COUNT(*) FROM accountbalances WHERE realline > 10000` = 465 | `… WHERE realline < -10000` = 442 |
| user-realised-pnl | For user U458616, what is the user's realised profit and loss, positive meaning a profit for the user? | `SELECT -realline FROM accountbalances WHERE TRIM(usertag) = 'U458616'` = -99,813.64 | `SELECT realline FROM accountbalances WHERE TRIM(usertag) = 'U458616'` = 99,813.64 |

- All six separate beyond the 0.01 relative tolerance (`write_line.yaml:177`). The smallest gap is 22 on 511, about 4.3%, on the first probe.
- None names the storage convention. "Positive meaning a profit for …" and "as a positive amount" fix only the answer's sign.
- usertag is padded to 36 characters, so `TRIM` is needed. U458616 occurs once.
- The probes are correlated through one sign, as the seeing probes were (`configs/write_line_thin.yaml:211-214`).
- Probe 4 must not be called "profit factor": that would add a named quantity.
- #152 may want a control-style check that the restricted figures in the table above do not appear among the answers. That is a suggestion, not a rule.

**Business term.** "realised profit and loss" is listed, as `write_line.yaml:77-79` requires (#61 design comment). The term-boundary displacement risk is disclosure 9 on #61.

**Realism case** (lever C condition (2), stated before injection).
- **Verified in the release:**
  - The column meanings call realline "A DOUBLE PRECISION realized PNL (e.g., -45.25)" and unrealline "… unrealized PNL (e.g., 120.75)" (`crypto_column_meaning_base.json`, lines 71-72). Neither states a sign convention.
  - KB 34 sets Profit Factor as Σ positive realline over |Σ negative realline|, the ratio of profitable to losing trades, so positive means profit (`crypto_kb.jsonl` line 35).
  - Clean data: realline 511 negative / 489 positive; unrealline 513 positive / 487 negative.
  - The balance columns are all positive: smallest walletsum 219.75, availsum 58.65, frozensum 161.10, margsum 1,024.90. Their sign fits either side's view, so the one house-side convention covers only the two P&L columns.
- **From the data, not a primary source:** realline and unrealline signs agree on 492 of 1,000 rows. From the columns checked, an answering agent cannot recover the convention by querying [inference].
- **General knowledge, not checked against a primary source:**
  - an exchange's or market maker's house book records the negative of the client's P&L;
  - credit-normal ledger extracts store income as negative;
  - client-facing exchange APIs mostly use positive for profit, which is why the agent defaults to it.
- **Both columns are flipped** so that the table's two P&L columns follow one convention. This is a convention that genuinely runs both ways, not a relabelling (#26).
- **Rating: medium.** A per-account table kept from the house side is less common than a client-side one.
- **Limit:** the case is shown to exist, not to be common.

**Disclosures for this slot** (numbered as on #61 where they match).
- **(3) First-run statistics used to choose the slot** (`results/thin/2026-10-24-66a86cb.jsonl`, as checked in the design fact-check):
  - confident variant: 10 of 10 samples wrote a value-meaning claim on realline; 8 of 10 committed to a sign direction (all but samples 2 and 5), at confidence .55 to .65;
  - abstain variant: 5 of 10 committed (samples 1, 2, 5, 6 and 8).
- **(4) Table reuse.** accountbalances was the table of the first freeze's wallet-sum defect. It is reused on a fresh clean copy, and walletsum stays as released.
- **(5) KB conflicts.**
  - KB 34 is reversed in the injected world.
  - KB 6 (line 7) and KB 30 (line 31) take realline as "the realized PnL", and KB 45 (line 46) builds on KB 30. Their conflict is an inference, since the sign there is implicit.
  - No KB entry mentions unrealline.
  - The agents do not see the KB. The claim writer is told "there is no documentation" (`warrant/agent/write_claims.py:42-43`).
- **(7)** The sign is injected and contradicts the release documentation, as seeing-recode did.
- **(8) The coverage cut and this table.**
  - The cut leaves 224 of accountbalances' 1,000 rows without their user. The table itself is not modified.
  - The probes are worded over balance records for this reason (see "What the coverage cut changes").
  - The user probe's U458616 is a Spot user.
- **(9)** Listing "realised profit and loss" risks a term-boundary claim taking this slot's place in sample 1. In the first run this happened on unrealline in 1 of 20 samples: confident sample 1, none of the abstain samples.
- **Not on #61's list:**
  - unrealline is flipped for coherence only; it has no slot and no probe;
  - the design's scratch input files `vm61/idsearch.sql` and `vm61/val_draft.py`;
  - the in-memory runs of `_defect` and `_disjoint`.

**Open risks.**
1. **Sample 1 may write no sign direction.** Such a claim is not addressed on both readings (`freeze/judge_rubric.md:41-42`), so agreement is low and the slot may not rank most confident.
2. **The judge has never labelled a value-meaning claim on "exchange's side" wording.** The validation on the two reference claims tests part of this.
3. **The after-injection VALUE wording is inferred.** It assumes DuckDB reads the column as text, which matched exactly on the clean data.
4. **An answerer may still join users despite the wording.** The restricted figures above let #154 see whether it did.
5. **Controls must stay off accountbalances, users, orders and its child tables** (#61 design comment).

**Read-only SQL run for this section.** All were run through `sqlite3` on `file:…/scratchpad/vm61/crypto_clean.sqlite?mode=ro`, plus `shasum -a 256` of the file (not SQL).
- `SELECT name, sql FROM sqlite_master WHERE name IN ('users','accountbalances')`
- `SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%REFERENCES users%'`
- `SELECT acctscope, COUNT(*) FROM users GROUP BY 1 ORDER BY 1`
- `SELECT COUNT(*), COUNT(DISTINCT userstamp), COUNT(DISTINCT TRIM(userstamp)), MAX(length(userstamp)), MIN(length(userstamp)) FROM users`
- `SELECT COUNT(*), SUM(u.userstamp IS NOT NULL) FROM accountbalances a LEFT JOIN users u ON u.userstamp = a.usertag`, and the same with `TRIM` on both sides
- `SELECT u.acctscope, COUNT(*) FROM accountbalances a JOIN users u ON u.userstamp = a.usertag GROUP BY 1`
- `SELECT a.usertag, u.acctscope, a.realline FROM accountbalances a LEFT JOIN users u ON u.userstamp = a.usertag WHERE TRIM(a.usertag)='U458616'`
- `SELECT COUNT(*), COUNT(DISTINCT usertag) FROM accountbalances`
- On `V = (SELECT -a.realline AS r, a.usertag, us.acctscope FROM accountbalances a JOIN users us ON us.userstamp = a.usertag)`:
  - `COUNT(*), SUM(r>0), SUM(r<0)`;
  - grouped by `acctscope='Margin'`: `COUNT(*)`, `SUM(r>0)`, `SUM(r<0)`, `-SUM(r)`, `SUM(r)`, `SUM(r) WHERE r>0`, `-SUM(r) WHERE r<0`, `SUM(r>10000)`, `SUM(r<-10000)`;
  - both profit-to-loss ratios, over all rows and over `acctscope<>'Margin'`.
- `SELECT typeof(realline), typeof(unrealline), COUNT(*) FROM accountbalances GROUP BY 1,2`
- `SELECT COUNT(*), COUNT(DISTINCT realline), COUNT(DISTINCT unrealline), SUM(realline IS NULL), SUM(unrealline IS NULL), SUM(realline=0), SUM(unrealline=0), COUNT(DISTINCT -realline), COUNT(DISTINCT -unrealline) FROM accountbalances`
- `SELECT col<0, COUNT(*), MIN(CAST(col AS TEXT)), MIN(CAST(-col AS TEXT)) FROM accountbalances GROUP BY 1`, for realline and for unrealline
- On `(SELECT -realline AS r, usertag FROM accountbalances)`: `SUM(r>0)`, `SUM(r<0)`, `-SUM(r)`, `SUM(r)`, `SUM(r) WHERE r>0`, `-SUM(r) WHERE r<0`, `SUM(r>10000)`, `SUM(r<-10000)`
- `SELECT usertag, -realline, length(usertag) FROM accountbalances WHERE TRIM(usertag)='U458616'`
- `SELECT SUM((realline<0)=(unrealline<0)), MIN(walletsum), MIN(availsum), MIN(frozensum), MIN(margsum) FROM accountbalances`

The design-time queries of the draft and the fact-check (Q1 to Q17, R1 to R13, and the identity search) are listed in `/private/tmp/claude-501/-Users-ryan-Warrant/a9079c7f-28f3-45fc-90ff-d78327932596/scratchpad/vm_design_check.md`, section "SQL run", and go into the note's full list.

## Conditions on the questions (#152)

The reading set's `holds` flags were set before the questions are written, so the questions are
bound by them. A configuration whose probes break either condition is re-authored, not run.

- **Formula slot:** no probe may ask what the extra amount is, or anything else whose gold answer
  differs under `cause-retries`, `cause-old-logger` or `cause-gateway`.
- **Coverage slot:** at least one probe must have a different gold answer under each of
  `closed-accounts`, `other-system` and `mistyped`, for example "How many margin accounts does the
  exchange hold?".
- **Value-meaning slot:** the probes ask over account balance records and fix the sign for the
  account holder. No probe joins to `users`.

## Disclosures

1. The coverage slot follows the natural design, because lever B was found infeasible. The read-only clean-copy queries used while designing all three slots are listed under "Clean-copy queries".
2. This freeze chose a realistic situation that is hard for the confidence rule. The formula slot's reading set was chosen knowing it lowers that slot's agreement.
3. First-run statistics were used to choose the slots (`results/thin/2026-10-24-66a86cb.jsonl`): on `realline`, 10 of 10 `confident` samples wrote a value-meaning claim and 8 of 10 committed to a sign, and 5 of 10 `abstain` samples committed; on `systemmonitoring`, no first-run claim named `exectimespan`, `apilatmark`, `queueline` or `rateremain`.
4. `accountbalances`, the first freeze's wallet-sum table, is reused on a fresh copy.
5. Release KB 34 and related entries contradict the negated profit and loss. The agents do not see the KB.
6. The formula relation is injected. It holds on no row of the clean copy, as wallet-sum's did.
7. The sign is injected and contradicts the release documentation (KB 34), as seeing-recode did.
8. The coverage cut leaves unmatched rows in `accountbalances`, the value-meaning slot's table, which is not modified.
9. Listing "realised profit and loss" as a business term risks a term-boundary claim taking the value-meaning slot's place in sample 1. In the first run, 1 of 20 samples did this on `unrealline`.
10. The alpha rule was written after the first run.
11. The order the tie-break seed 20261012 gives is already known from the first run.
12. Every battery-only trial is listed under "Design trials", as `CONTRIBUTING.md` requires.
13. The blind auditor could read the first run's key once it was public (#146), so the audit may show a learning effect.

## Design trials

One battery-only trial, run on 2026-10-28 after the reading-set rule was written and posted on #61,
on a scratch copy of the crypto clean database outside the data directory (SHA-256 `49103c15…a5e1`,
the freeze's). No model was called. It used the project's own code, not a stand-in:
`warrant.defects.build.build` on this file's three defects, then `warrant.write_line.predict.predict`
with this file's battery settings, then `warrant.write_line.warrants.slot_warrants`, and a second
battery run on the clean copy for comparison. The two scripts are in `freeze/NOTE_2_queries.md`.

**Results.**

- **Audits.** `exec-throttle` changed 1,000 rows of `systemmonitoring`; the relation holds on 901 of
  1,000. `margin-cut` took `users` from 1,000 to 776 rows. `pnl-sign` changed 1,000 rows of
  `accountbalances`, with 2,000 one-to-one recodings.
- **Predicted outcomes, as designed:** `exec-throttle` agent alone, `margin-cut` both, `pnl-sign`
  person only, so k = 2.
  - `exec-throttle`: `as-released`, `sum-everywhere` and `retry-rows` differ from the true reading's
    output; the three cause readings do not, and all three hold.
  - `margin-cut`: `nothing-cut`, `cut-with-children` and `options-cut` differ; the three provenance
    readings do not, and all three fail.
  - `pnl-sign`: neither reading differs; the rival fails.
- **The bridge:** the battery tells both data-part drift readings from the true reading, and cannot
  tell the convention drift reading apart.
- **#50's warrant rule** accepts all three slots: formula data and data, coverage none and testimony
  ("a record of how the data came to be could settle it"), value meaning none and declaration. So the
  real run will not refuse them (`warrant/write_line/warrants.py:89`).
- **The formula finding**, word for word: "exectimespan equals apilatmark + queueline for 90.1% of
  the 1,000 rows where it is non-zero. On the remaining 99 it exceeds the sum, so at least one further
  component contributes to exectimespan and is not present in this data. Any breakdown built from
  apilatmark + queueline alone is incomplete for those rows." It names no subgroup.
- **Every difference between the clean and the injected output** is one the design expects:
  - the RULE finding above;
  - on `users`: GRAIN counts 1,000 to 776, and the VALUE code list loses Margin ("Holds 3 distinct
    values: Spot (287), Futures (246), Options (243)");
  - the LINK findings on `accountbalances.usertag` and `orders.userlink` go from 100% matched to
    77.6% and 77.68%, each with an unmatched-rows finding (224 and 223 rows);
  - the clean copy's one coverage-bearing finding on `users`, "1 of 1000 users.userstamp values are
    never referenced by orders.userlink", is gone, as the confounding check expected;
  - the VALUE findings on `realline` and `unrealline` swap their format classes.

  No other finding changed. Finding counts on the injected copy: GRAIN 47, VALUE 21, LINK 11,
  LIMIT 2, RULE 2.

No clean scan was run, so the first freeze's committed scan in `docs/research/` is untouched.

## Clean-copy queries

- The queries run while writing each defect are listed in its section above.
- The queries of the lever-B search and of the formula search, run by sub-agents on 2026-10-28, are
  in `freeze/NOTE_2_queries.md`, as they were recorded.
- The earlier analysis of 2026-10-25 (the location and lever studies) also queried the clean copies
  read-only; the counts it gave are cited where they are used.
- Every query ran on copies whose SHA-256 matches `release.sha256.crypto` or `release.sha256.alien`,
  opened read-only. None ran on an injected copy.
