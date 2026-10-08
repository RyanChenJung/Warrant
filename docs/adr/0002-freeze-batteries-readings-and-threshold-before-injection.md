# Freeze the check batteries, reading sets and confidence threshold before injecting any defect

We inject the defects ourselves, so any check, reading or threshold chosen after the defects exist can
be fitted to them, which would manufacture both the predicted outcomes and migration. The baseline
battery is therefore detectors that existed before this project's defects were designed (Gloss), used
with their logic unchanged and connected only through an adapter; the extended battery's cross-table
checks are committed before the first defect is generated; each claim's reading set is written down
at injection and frozen with the batteries; and the confidence threshold for the confidence-based
allocation rules is tuned on databases outside the showcase set to favour the baseline, then frozen.

## Considered Options

- **Write a new battery from scratch.** It would fit multi-table databases better, but nothing could
  show it was not shaped by the defects already planned in design discussions.
- **Fix the threshold at a round number, or choose it after seeing results.** A round number has no
  defensible source; choosing afterwards lets the baseline be made to look as weak as we like.

## Consequences

- Bugs found in Gloss during the first week may be fixed only before the first defect is generated,
  and every fix is committed. If Gloss cannot run on the chosen databases at all, its detector logic
  is ported into this repo unchanged, changing only how data is read.
- The commit history is the evidence of order: batteries and reading sets first, defects after.
- The full curve over all thresholds is reported in an appendix next to the frozen threshold.
