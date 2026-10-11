# The headline is a claim's lifecycle, tested one end at a time

The headline widens from the write allocation rule to the claim's lifecycle: a claim's warrant
decides who may write it, what can detect that it has gone stale, and whom to ask. One partition of
a claim's reading set under a frozen check battery predicts all three. Both lines use one
knowledge-store format and one model, so a write-only headline would leave the maintenance line as
an unconnected second study. The thin version committed for December tests each end separately and
in turn: first the write line, on who should write, then the maintenance line, on what happens when
a stored claim goes stale and when to ask a person. The bridge between the two ends says that the
partition which decides whether a claim is settled also decides whether a check battery can detect
its data-part drift. It is pre-registered through each injected defect's drift reading (ADR 0007),
and its full test is future work.

The headline, the hypothesis roles (spec issue #26) and one fallback headline (the write line's
claim, ADR 0001) with two feasibility triggers are fixed before any result exists. There are two
confirmatory tests, one per line, both at a matched number of questions to a person: on the write
line, the settlement rule against the confidence rule; on the maintenance line, warrant-routed
escalation against confidence-escalate, on silent errors in the drift tasks the team writes on the
benchmark's knowledge base. Everything else is descriptive: whether predicted and measured
allocation outcomes agree (H1; there are too few defects per claim kind for a test), the harm of
stored answers against no memory (a manipulation check), whether the agent looks things up without
being told, the accuracy ceiling with the full knowledge base in the prompt, token cost, and every
result on the write line's claims carried into drift.

Each fallback is triggered by feasibility, meaning whether a line has produced a result by a date,
never by what a result says:

- If the full thin write-line run is not complete by November 16, the maintenance line is dropped
  and the headline falls back to the write line's claim, the allocation rule of ADR 0001, with the
  bridge registered as theory only. The full run means all five allocation rules on all frozen
  defects, at least one run each, with the real model rather than the scripted fake agent used in
  tests. The minimal pilot does not count.
- If the maintenance line has no result by November 30, the headline falls back to the write line's
  claim.

This amends ADR 0001: its allocation rule becomes the write end of the headline, and its
requirement to measure agent answers, not only the checks' output, still holds.

## Considered Options

- **Keep the write-only headline.** The thin version could test it in full, but the joint
  prediction, the one thing neither line has on its own, would never be stated before results, and
  the maintenance line would read as a separate study.
- **Run both lines in parallel, split by people.** Each line would get more calendar time, but both
  depend on the write line's freeze, harness and scoring: the maintenance line carries the write
  line's claims into drift and keeps them in the same knowledge-store format. Splitting about 35
  person-hours a week across two lines would leave that shared path half-staffed, and either line
  could miss its date. Running the lines in turn makes the write line's claim the floor the headline
  falls back to.
- **Decide the headline after preliminary results.** Rejected: picking whichever line looks better
  is a forking path, and it conflicts with the freeze discipline of ADR 0002, since a headline
  chosen after results can be fitted to them like a check chosen after the defects. The pilot's
  results arrive on November 2, the date such a choice would be made, so nobody could show the
  choice ignored them.

## Consequences

- The work is sequential, and the whole team starts on the write line, split by module rather than
  by line. From October 12 to November 2 the write line freezes its three defects (one per claim
  kind: coverage, column formula, value meaning), computes their predicted outcomes and runs a
  minimal pilot. The freeze is hard; if it misses November 2 it moves to November 9 at the latest.
  The predicted outcomes and the pilot are targets with a cap of November 9, and together they are
  the November 2 course results deliverable. A velocity checkpoint on October 17 compares progress
  with the estimates. The full thin write-line run and its analysis follow from November 3 to 16,
  the thin maintenance line from November 17 to 30, and December 1 to 7 is for writing.
- The headline claims more than the thin version tests. The paper presents the bridge as a
  pre-registered prediction. The thin maintenance line carries the write line's three claims into
  drift through their frozen drift readings: the coverage and column-formula claims through
  data-part drift on the drift reading's database, the value-meaning claim through convention drift
  with identical data. These results are descriptive. The coverage claim, whose readings the
  check battery narrows and a person picks among, carries a testimony warrant, which a stronger
  battery could later turn into a data warrant. The full warrant kind by drift type matrix comes
  after December.
- The confirmatory maintenance test runs on convention drift only, so it can show where confidence
  is blind but not that confidence does better under data-part drift. The two carried claims with
  data-part drift show that contrast descriptively at most; testing it needs the full joint test.
- Drift readings are declared before injection even if the maintenance line is dropped, because a
  drift reading added afterwards could be chosen to confirm the bridge (ADR 0007).
