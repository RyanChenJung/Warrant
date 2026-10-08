# Documentation proposes claims, and the data can only veto the data part

The agent may write a claim taken from documentation if the check battery finds nothing in the data
that contradicts it, citing the source; contradicted claims go to a person. For convention-part
claims such as value meaning and term boundary, whose readings leave the database identical, the data
can never contradict the documentation, so this check passes vacuously and stale documentation slips
through. The experiment keeps the uniform rule so that the gap becomes a tested prediction (stale
documentation is caught for coverage and grain, not for value meaning or term boundary), while the
thesis recommends that a person confirm documentation-backed convention claims unless the source is
an authoritative record.

## Considered Options

- **Treat documentation like a person.** Rejected: the agent would copy stale documentation, the
  most common failure in enterprise data.
- **Require person confirmation for convention claims in the experiment as well.** Rejected for the
  experiment: it would remove the evidence that the uniform rule fails there.
- **Give the agent no documentation.** Rejected: reviewers would ask why the agent does not simply
  read the data dictionary.

## Consequences

- Documentation is read when claims are written, not when probe questions are answered.
- Stale documentation is produced by injecting a defect into the data and leaving its documentation
  unchanged.
- Before the showcase the documentation condition runs only with the extended battery.
- Treating an authoritative record as its owner's declaration rests on Searle; the support for
  written rules as standing declarations still needs the primary text (see
  `docs/research/2026-10-08-theory-frame.md`).
