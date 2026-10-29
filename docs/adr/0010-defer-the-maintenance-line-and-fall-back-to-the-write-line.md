# Defer the maintenance line; the headline falls back to the write line's claim

The team agreed on 2026-10-19 to pause the maintenance line: no further tickets, paper sections or
slides for it, and its tickets marked as future work. The headline falls back now to the write
line's claim, the allocation rule of ADR 0001: at a matched number of questions to a person, asking
where the frozen check battery cannot settle a claim leads to fewer wrong answers than asking where
the agent is least confident. The reason is capacity: the team's time goes to the write line's full
thin run (#54), the course deliverables and the October 28 presentation. No result decided this. The decision came
before the pilot (#49, 2026-10-20), the first real-model result on the frozen defects, and no
maintenance result existed.

The maintenance line may resume if time allows after the week of October 19. If it does, the
decision is recorded with its date, and the headline stays the write line's claim whatever either
line's results show; maintenance results are then reported in addition to it, not in its place.
Choosing the headline after seeing results is the forking path ADR 0006 rejects.

This amends ADR 0006: its fallback headline applies now by this decision instead of by its
November 16 feasibility trigger, and its maintenance confirmatory test (warrant-routed escalation
against confidence-escalate) is not run in the thin version.

## Considered Options

- **Keep both lines as planned.** The maintenance line was due to start on November 17 after the
  write line's full run. With the write line's chain (#50, #51, #54) still ahead and the course
  deliverables in parallel, both lines would compete for the same people, and the write line is the
  one the other depends on.
- **Drop the maintenance line and remove its work.** Rejected: its pre-registered parts (the drift
  readings frozen with the write line, the bridge predictions committed with #37, the documented
  drift tasks of #43) are what would let it resume without a forking path, and removing them would
  throw that away.

## Consequences

- The maintenance tickets (#44 to #48, #55, #56) carry the `future-work` label and stay open; no
  code, task or committed prediction is removed.
- The drift readings in the freeze and the bridge predictions in `predictions/` stay as committed.
  The paper presents the bridge, and the claim that a claim's warrant also decides how it is
  maintained, as pre-registered predictions left for future work.
- The write line has two confirmatory tests, each the settlement rule against the confidence rule
  at matched asks (ADR 0007), one per freeze (amended 2026-10-28, #61).
  - The first freeze's test is the primary one. Its rules coincided, so it is recorded as not run
    (#54).
  - The second freeze's test (ADR 0011) is reported next to it, not pooled.
  - Its alpha is 0.05, by a rule written after the first run. Had the first freeze's test run, each
    test would have been at 0.025. It did not, so the second is at 0.05. The family-wise error rate
    is at most 5% either way.
  - If the second freeze's rules coincide too, that is reported as it is, and no third freeze is
    added.
- The spec (#26) keeps its maintenance sections as the plan for a resumed or later study; the
  decision is recorded there.
