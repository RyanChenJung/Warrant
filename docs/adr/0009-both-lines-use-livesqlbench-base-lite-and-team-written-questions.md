# Both lines use LiveSQLBench-Base-Lite, and the team writes every question and its gold SQL

Both lines use the SQLite release of LiveSQLBench-Base-Lite (`birdsql/livesqlbench-base-lite-sqlite`
on Hugging Face, public under CC BY-SA 4.0), the single-turn benchmark BIRD-Interact LITE is built
on. For each database it provides a template SQLite file (`<db>_template.sqlite`), column meanings
(`<db>_column_meaning_base.json`) and a business knowledge base (`<db>_kb.jsonl`), the kind of
knowledge this project studies. One dataset for both lines is what lets the same claims be carried
from writing into drift (ADR 0006). The team writes all questions and gold SQL for both lines: the
write line's probe questions on its injected copies and the maintenance line's drift tasks on the
knowledge base. No BIRD-Interact task, no withheld ground truth and no PostgreSQL database is used,
so everything the team makes can be committed to this public repo. Week one checks the candidate
databases for additive numeric columns, coded value columns and status columns, which the
column-formula, value-meaning and coverage defects need; if none fit, the write line falls back to
BIRD dev, and the maintenance line's drift tasks stay on the LiveSQLBench-Base-Lite knowledge base
they are written on.

There is no private dataset. The database each reading would produce is rebuilt deterministically
from the public SQLite files and the transformations committed here; large database files are never
committed. Code is under MIT. Every data file derived from LiveSQLBench (edited knowledge-base
entries, defect specifications, drift tasks) is under CC BY-SA 4.0, with attribution in the README.

The benchmark's knowledge base is treated as the authoritative record, by stipulation: it stands in
for a glossary with a named owner. A claim the knowledge base states can therefore carry a record
warrant tied to its entry's version, and a constant or threshold that changes with a new version of
its entry is documented convention drift.

## Considered Options

- **BIRD dev, as spec issue 6 planned.** Rejected as the main dataset: it has column and value
  descriptions but no business knowledge base, and it has been public and widely used since 2023,
  so models have likely memorised it. Kept as the write line's week-one fallback; with no
  knowledge base, it cannot hold the maintenance line's drift tasks.
- **BIRD-Interact LITE.** Rejected: its value is its interaction protocol, which this project does
  not use (ADR 0008), and running its tasks without that protocol invites the obvious objection that
  the benchmark is used outside the setting it was built for.
- **Spider 2.0.** Rejected: too heavy for the thin version.
- **The PostgreSQL release, one database per reading.** Rejected: each reading would need its own
  database on a server and a reset between runs, while SQLite files are cheap to build, compare and
  discard.
- **A private dataset holding the per-reading databases.** Rejected: with public data and no
  withheld ground truth nothing needs to stay private, and deterministic rebuilds make stored copies
  unnecessary.

## Consequences

- Spec issue 6's data plan (BIRD dev with its description files, BIRD train for tuning) no longer
  applies, except BIRD dev as the fallback. A loader for the SQLite files, column meanings and
  knowledge base is needed.
- The freeze files, questions, gold SQL and drift tasks are all the team's own, so they are public
  from the freeze, as ADR 0007 (d) requires, and every result can be reproduced from this repo and
  the public SQLite release.
- The column meanings stay ordinary documentation: written by others, they warrant only the data
  part of a claim the data does not contradict (ADR 0004).
- Limitation: real documentation varies in authority. This knowledge base was written by the
  benchmark's authors, not by whoever sets the conventions it states, so the record-warrant results
  hold for a record whose authority is stipulated.
- Limitation: the databases may be more synthetic than BIRD's.
