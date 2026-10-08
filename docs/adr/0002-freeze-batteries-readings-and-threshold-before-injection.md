# Freeze the check batteries, reading sets, confidence threshold and outcome cutoffs before injecting any defect

We inject the defects ourselves, so any check, reading, threshold or cutoff chosen after the defects
exist can be fitted to them, which would manufacture both the predicted outcomes and migration. The
baseline battery is therefore checks that existed before this project's defects were designed (Gloss,
the author's own detector library, pinned to a recorded commit), used with their logic unchanged and
connected only through an adapter; the extended battery's cross-table checks are committed before the
first defect is generated; each claim's reading set is written down and committed before its defect
is generated; the confidence threshold for the confidence and hybrid rules is tuned on databases
outside the showcase set to favour the confidence rule, then frozen; and the cutoffs that turn the
two contributions into allocation outcomes, with the way per-claim predicted outcomes combine into
one prediction per claim kind, are fixed at the same time.

## Considered Options

- **Write a new battery from scratch.** It would fit multi-table databases better, but nothing could
  show it was not shaped by the defects already planned in design discussions.
- **Fix the threshold at a round number, or choose it after seeing results.** A round number has no
  defensible source; choosing afterwards lets the confidence rule be made to look as weak as we like.

## Consequences

- Bugs found in Gloss during the first week may be fixed only before the first defect is generated,
  and every fix is committed. If Gloss cannot run on the chosen databases at all, its detector logic
  is ported into this repo unchanged, changing only how data is read.
- This repo's commit history, together with the pinned Gloss commit, is the evidence of order:
  batteries, reading sets, threshold and cutoffs first, defects after. Outside readers can check the
  baseline battery only if the Gloss detectors used are published.
- The full curve over all thresholds is reported in an appendix next to the frozen threshold.
