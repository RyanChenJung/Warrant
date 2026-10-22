# Write claims under two prompts: stated confidence is primary, not guessing is descriptive

Decided on 2026-10-22, before any claim-writing call. The write-claims prompt is not part of the
freeze; it is committed and pushed before its first call (#50). The full run (#54) writes claims
under two variants of it, which differ only in their last instruction:

- **`confident`, the primary variant.** The agent writes every claim it would make, including ones
  it is unsure of, and lets its stated confidence say how sure it is. The write line's confirmatory
  test, the settlement rule against the confidence rule at matched asks (ADR 0007), uses the stores
  built from this variant's samples.
- **`abstain`, a descriptive variant.** The agent writes only what the data supports and nothing it
  would only be guessing. This is the instruction most systems give an agent: do not guess, and
  leave it to a person when unsure. Its stores and the same comparison are reported descriptively,
  with no test.

**Why both.** Each variant lets the agent express its own uncertainty. Under `abstain` it does so by
writing nothing, which the frozen confidence rule ranks least confident. Under `confident` it does
so by consistency across samples and a stated confidence. Either way the allocation rests on the
agent's self-assessment, while the settlement rule rests on what the frozen battery settles. Running
both shows whether a result holds for both ways an agent says it is unsure.

**Why `confident` is primary.**
- **Ties.** Under `abstain`, slots without a sample-1 claim tie at least confident, and the seeded
  permutation, not confidence, orders them.
- **Coinciding.** The two rules then most likely coincide (ADR 0011), and the confirmatory test does
  not run.
- **Information.** `confident` gives the frozen rule both of its keys, agreement and stated
  confidence, to rank by.

**How the run is laid out.**
- **Rule ids.** `empty` and `all_person` do not depend on claim writing and are shared. Under
  `confident` the rules are `all_agent`, `settlement` and `confidence`; under `abstain` they are
  `all_agent_abstain`, `settlement_abstain` and `confidence_abstain`.
- **What each variant gets.** Each has its own 2 × 10 claim-writing samples and their judgements,
  with the same k = 2, the same reading orders and the same tie-break seed.

## Considered Options

- **Only `confident`.** Rejected: it would leave out the practice most systems follow.
- **Only `abstain`.** Rejected: the confirmatory test would most likely not run, and the ranking of
  the unsettled slots would come from the seeded permutation.
- **Both, with `abstain` primary.** Rejected for the same reasons.
- **Both as confirmatory tests.** Rejected: two tests would need a multiplicity adjustment, and
  picking the one to headline after seeing the results is the forking path ADR 0006 rejects.

## Consequences

- **#50** builds both variants. The sample and judgement records carry the variant (#53's record
  format).
- **#54** runs both. The extra claim writing, judging and about 300 answers cost about $15, inside
  #54's $100 cap.
- **#53** reports the `abstain` variant descriptively next to the primary results: its
  contributions, its wrong-writes curve, and whether its two rules coincide.
- **The blind audit (#123)** covers the primary variant's claims. The `abstain` variant's claims are
  judged but not audited.
- This extends ADR 0007 (matched asks) and ADR 0011 (the configuration frozen at the first
  claim-writing call, which now covers both variants) and amends neither.
