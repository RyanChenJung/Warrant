# Freeze the full run's configuration at its first model call, and add slots only on a date

Two rules for the write line's full thin run (#54), decided on 2026-10-21 before any agent claim
was written. Both are fixed now because changing them after results exist would be fitting the
study to its answers.

**The run's configuration is frozen at its first model call.** `configs/write_line_thin.yaml` holds
the questions, their gold SQL and reading tags, the business-term list and the model settings (#52).
It is not edited after the run's first model call. A question found unscorable during the run stays
as it is: its problem is disclosed, and results are reported with and without it. Every result
record carries the configuration's SHA-256, and a stopped run is resumed under its run id rather
than started again (#53). Claim writing samples at the model's default, so restarting would draw a
different claim set. A configuration that changed mid-run would leave one run with several
versions of its questions, and a change made after seeing answers would look like fitting.

**A second freeze with three more slots is authored if, and only if, the first complete pass of
the full run finishes by 2026-11-16.** That freeze is stage 1 of #61: a second defect per claim
kind. The condition is the date alone; no result of the first freeze enters it.
- **Why add slots at all.** With three slots and k = 2, the settlement and confidence rules can
  differ on at most one slot. #50's decision that the claim-writing prompt names no slot makes it
  likely that they do not differ at all, since the two unsettled slots then probably get no agent
  claim and rank least confident, which is what the freeze reports as "rules coincide".
- **How the slots enter.** As decided on #57 (2026-10-17 and 18), the new defects go in a second
  freeze, committed and pushed before they are injected. They are designed after seeing the first
  run, so their confirmatory test is reported separately, not pooled with the first freeze's.

## Considered Options

- **Configuration:**
  - *Allow edits during the run, recording each version's hash on #54.* Rejected: the three runs
    would answer different question sets, and the summary would have to split by version.
  - *Freeze it at the first model call.* Chosen. `--check` and review catch problems before the run
    instead.
- **Slots:**
  - *Add none.* Rejected: the write line's only confirmatory test would most likely not run, or rest
    on a single slot.
  - *Add slots only if the first freeze's rules coincide.* Rejected: the condition would depend on
    data the run produces, the forking path ADR 0006 rejects for the headline.
  - *Add them before the full run.* Rejected: it would delay the first complete pass past
    2026-11-16, and the first freeze is already committed.
  - *Add them if the first pass finishes by a fixed date.* Chosen. The condition is fixed in
    advance and depends only on feasibility, as ADR 0006's fallbacks do.

## Consequences

- #52 settles `configs/write_line_thin.yaml` before the run's first model call. The run (#54)
  refuses to resume with another configuration hash.
- #54 records on #26 the time its first complete pass finishes, since that time decides #61.
- If the date holds, #61 (ready-for-human) is authored by the lead, with its own probes, its own
  budget line next to #54's $100 cap and its own confirmatory test. If it does not, #61 becomes
  future work, and the write-up reports the first freeze alone, including "rules coincide; H3 not
  tested at write time" if that is the result.
- This extends ADR 0006 (feasibility triggers fixed in advance) and ADR 0007 (commit order) and
  amends neither.
