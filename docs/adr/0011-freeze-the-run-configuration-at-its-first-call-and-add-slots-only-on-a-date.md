# Freeze the full run's configuration at its first model call, and add slots only on a date

Status: amended by ADR 0013.

Two rules for the write line's full thin run (#54), decided on 2026-10-21 before any agent claim
was written. Both are fixed now because changing them after results exist would be fitting the
study to its answers.

**The run's configuration is frozen at its first model call.** That call is the run's first
claim-writing call; the judge's validation ran earlier under the pilot's configuration.
- **What is frozen.** `configs/write_line_thin.yaml` will hold the questions, their gold SQL and
  reading tags, and the business-term list (#52). It also holds the model settings fixed before the
  pilot (#49). It is not edited after the run's first model call.
- **An unscorable question stays.** If a question is found unscorable during the run, it stays as it
  is and its problem is disclosed. The analysis with every question as frozen is the confirmatory
  one; the analysis without that question is descriptive.
- **This departs from the pilot's rule.** The pilot changed a question the harness could not score,
  recorded the change and committed it again before the next call. The full run does not follow
  that rule.
- **Why.** Every result record carries the configuration's SHA-256, and a stopped run is resumed
  under its run id rather than started again (#53). Claim writing samples at the model's default, so
  restarting would draw a different claim set. A configuration changed mid-run would leave one run
  with several versions of its questions, and a change made after seeing answers would look like
  fitting. `--check` and review catch problems before the run instead.

**A second freeze with three more slots is authored if, and only if, the first complete pass of
the full run finishes by 2026-11-16.** That freeze is stage 1 of #61: a second defect per claim
kind.
- **When the pass counts as finished.** Every (question, rule) of the configuration has a run-0
  answer record under the run's first run id, scored or recorded as a failure after retries. Its
  time is the latest such record's timestamp. The pass meets the date if that time is at or before
  2026-11-16 23:59 America/Chicago (2026-11-17 05:59 UTC). The condition is the date alone; no
  result of the first freeze enters it.
- **Why add slots.** The committed predictions leave two slots to a person (only wallet-sum is
  predicted agent alone), so k = 2.
  - With three slots, each rule then leaves exactly one slot to the agent. The two stores either
    coincide or swap one slot, and the comparison rests on that one swap.
  - #50's decision that the claim-writing prompt names no slot makes coinciding likely. The two
    unsettled slots then probably get no agent claim and rank least confident, which is what the
    freeze reports as "rules coincide".
  - The new defects are chosen where the agent is likely to write a confident claim that is wrong,
    the case on which the two rules diverge and which the write line's claim is about. One example
    is a familiar-label swap, such as Excellent and Poor exchanged.
- **How they enter.** As decided on #57 (2026-10-17 and 18), the new defects go in a second freeze,
  committed and pushed before they are injected. They are designed after seeing the first run, so
  their confirmatory test is reported separately, not pooled with the first freeze's. The first
  freeze's matched asks and test stay as frozen over its three slots. The second freeze fixes,
  before any model call on its defects, its own k from its own committed predictions, its matched
  asks and how its test is reported next to the first. Its k cannot be fixed before its injection:
  the predictions are computed on the injected copies (amended 2026-10-28, #61). It runs under its
  own configuration and run id.

## Considered Options

- **Keep the pilot's rule for the configuration.** Rejected: under that rule, a question the harness
  cannot score is changed, recorded and committed again before its next call. The three runs would
  then answer different question sets, the summary would have to split by version, and a resume
  could not check one configuration hash.
- **Add no slots.** Rejected: the write line's only confirmatory test would most likely not run, or
  would rest on one swap of two slots.
- **Add slots only if the first freeze's rules coincide.** Rejected: the condition would depend on
  data the run produces. That is the forking path ADR 0006 rejects for the headline.
- **Add the slots before the full run.** Rejected for three reasons:
  - The first freeze was committed without them, by the decision of 2026-10-17, to keep the
    November 2 margin (#57).
  - #61 needs the thin run first, and defects designed after it can use what it shows.
  - Adding them now would also delay the first complete pass past 2026-11-16.

  The cost of waiting is that their test cannot be pooled with the first freeze's.

## Consequences

- #52 settles `configs/write_line_thin.yaml` before the run's first model call. The run's resume and
  the summary (#53) refuse records with another configuration hash.
- #54 records on #26 the timestamp at which its first complete pass finished, since that timestamp
  decides #61.
- **If the date holds,** the lead designs #61 (ready-for-human) and #52's owner writes its probes. Its
  model calls sit under their own cap of $80, set in its run configuration, against an estimate of
  about $40, next to #54's $100 cap (amended 2026-10-28, #61).
- **If the date does not hold,** #61 becomes future work. The write-up then reports the first freeze
  alone, including "rules coincide; H3 not tested at write time" if that is the result.
- **The role of November 16.** Since ADR 0010, that date triggers no fallback; this ADR gives it its
  only remaining role.
- **Two confirmatory tests.** If the date holds, the first freeze's test stays the primary
  confirmatory test (ADR 0010), and the second freeze's test is reported separately. How the two
  tests are read together is the alpha rule recorded in ADR 0010, written before the second
  freeze's injection (amended 2026-10-28, #61).
- This extends ADR 0006 (feasibility triggers fixed in advance) and ADR 0007 (commit order) and
  amends neither.
