# Copy the baseline battery into this repo, compare at matched asks, freeze drift readings, and let the commit history show order

ADR 0002's reason stands: we inject the defects ourselves, so anything chosen after they exist can
be fitted to them. This amends four of the means ADR 0002 chose, to fit the scope committed for
December (the thin version) and to keep the joint test of ADR 0006 possible:

- **(a) Baseline battery.** The Gloss detectors that form the baseline battery are copied into this
  repo with their logic unchanged and are called directly. The copy is taken from a public Gloss
  release: a public repository with a fresh history, whose provenance names the private original
  commit it was prepared from. The vendoring note cites the release's repository and commit and the
  private original commit. The only glue is a data export, not an adapter: it writes each table to
  CSV and passes the declared-foreign-key peer set. There is no runtime dependency on Gloss. The
  frozen battery has to sit in the repo whose push history is the evidence of order (d), so that it
  cannot change or vanish upstream after the freeze; the public release lets any teammate vendor it
  and any reader check the copy against it.
- **(b) Confidence rule.** It is compared with the settlement rule at a matched number of questions
  to a person: it sends to a person as many claims as the settlement rule does, its least confident
  ones. No threshold is tuned on separate databases. The comparison then tests which claims each
  rule sends to a person rather than how many, the same matching the maintenance line's escalation
  comparison uses.
- **(c) Drift readings.** Each defect's drift reading is declared and frozen with its reading set
  before the defect is injected. The bridge prediction is pre-registered through them, and a drift
  reading added after injection could be picked to confirm it.
- **(d) Evidence of order.** The freeze commit is pushed to this public repo before any defect is
  injected, and GitHub's timestamp is the evidence that the freeze came first. The data is public
  and no withheld ground truth is used (ADR 0009), so nothing in the freeze files needs to stay
  private. This replaces the runtime guard that refused to run if a frozen file had changed,
  machinery sized for the full study rather than the thin version.

Still required from ADR 0002: the baseline's detector logic predates the defects and does not
change, except that bugs may be fixed before the first injection, each in its own commit, and how
the detectors read data may change if they cannot read the chosen databases. Reading sets, the
confidence combination rule, the judge method that decides when two claims agree, the outcome
cutoffs and the rule that combines per-claim predicted outcomes into one per claim kind are frozen
before the first defect is injected.

## Considered Options

- **Keep Gloss as a pinned external dependency on the public release.** Rejected: it would be
  installable and checkable, but the frozen battery would then live outside this repo, whose push
  history is the evidence of order, and an upstream change or deletion after the freeze would not
  show in it.
- **Copy from the private Gloss repository.** Rejected: only its author can read it, so no teammate
  could vendor the battery, and readers could not check the copy against its source.
- **Keep tuning the threshold on separate databases with their own defects.** It gives the
  confidence rule its best threshold, but needs a second set of databases and defects the thin
  version cannot afford, and its ask count would differ from the settlement rule's, mixing how many
  claims go to a person with which ones.
- **Keep the runtime guard.** It blocks an edit after injection instead of only recording it, but
  costs more than the thin version can spare for evidence the public commit history already gives.

## Consequences

- The matched number is the settlement rule's ask count, which the predicted outcomes fix before
  any agent runs. Under the baseline battery few claims are settled, so the comparison rests on the
  few claims where the two rules can differ.
- The curve of wrong writes against questions to a person over every confidence cutoff is still
  reported, with the settlement rule as one point.
- The hybrid rule needs a threshold and is future work; when it returns, its threshold must be fixed
  before the defects it runs on are injected.
- The extended battery is future work, but ADR 0002's requirement that its checks be committed
  before the first defect still stands: if it is written later, migration can be measured only on
  defects injected after it.
- A reader checks order by finding that the freeze commit reached GitHub before the first commit
  that records an injection. A freeze file edited after injection is not blocked, only visible.
- Only the detectors and what they need to run are copied; nothing from the data Gloss was first
  built on enters this public repo.
