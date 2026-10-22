# Warrant

**Which questions should a data AI ask an expert on day one?**

Before a data AI has any users, it gives wrong numbers, without warning, wherever the data cannot
show what it means. This repo tests one way to choose what to ask the person who knows the
business: run automatic checks on the data first, and ask only about what they cannot settle. With
the same number of questions, we compare it with asking where the AI is least confident.

In the terms of [CONTEXT.md](CONTEXT.md): which claims about a dataset the check battery can settle
on its own and which need a person
([ADR 0001](docs/adr/0001-headline-claim-is-an-allocation-rule.md)). The maintenance line, on
keeping claims current, is paused
([ADR 0010](docs/adr/0010-defer-the-maintenance-line-and-fall-back-to-the-write-line.md)).
Decisions are recorded in [docs/adr/](docs/adr/).

## Data and licences

Both lines use **LiveSQLBench-Base-Lite**, in its SQLite release
([`birdsql/livesqlbench-base-lite-sqlite`](https://huggingface.co/datasets/birdsql/livesqlbench-base-lite-sqlite)
on Hugging Face, pinned to revision `0664a2f28555faa0dd2947c8c23288df79bcc06b` in
[configs/livesqlbench-base-lite.yaml](configs/livesqlbench-base-lite.yaml)), maintained by the
BIRD Team at HKU and Google Cloud and published under CC BY-SA 4.0. Its paper is linked from the
dataset card ([2510.05318](https://huggingface.co/papers/2510.05318)).

The databases are not redistributed: `uv run python -m warrant.data.fetch` downloads them into the
data directory (`$WARRANT_DATA_DIR`, by default `~/.cache/warrant`), and no database file is
committed. The project changes the dataset in these ways: defects injected into copies of its
databases, as specified in the freeze; knowledge-base entries edited for drift tasks; and questions
and drift tasks written by the team.

Code and documentation are under the MIT licence ([LICENSE](LICENSE)).

### Data derived from LiveSQLBench-Base-Lite

Files that hold data derived from the release, such as its table and column names, codes, counts,
column meanings or knowledge-base entries, are licensed under CC BY-SA 4.0
([LICENSE-DATA](LICENSE-DATA)). They are:

- `freeze/`: the freeze files with the defect specifications (#34).
- `docs/research/2026-10-11-week-one-database-check.md` and
  `docs/research/week-one-database-check.json`: the week-one check of the candidate databases (#59).
- `docs/research/2026-10-13-clean-scan.md`, `docs/research/clean-scan.json` and
  `docs/research/clean-scan-runtimes.json`: the clean-database scan of the battery (#30).
- `predictions/`: the predicted outcomes under the baseline battery, with the normalised battery
  output of every reading database (#37).
- `configs/write_line_pilot.yaml`: the write line's pilot probes, with their gold SQL (#49).
- `configs/write_line_thin.yaml`: the write line's probe and control questions for the thin run, with
  their gold SQL and the business-term list (#52).
- `docs/talks/`: the shared facts for talks, with the planted problems' tables, counts and codes.
- `results/`: stored results of real-model runs, with their SQL and, after the pilot (#49), their
  executed results.
- `drift_tasks/`: the maintenance line's documented drift tasks, with edited knowledge-base entries
  (#43).
- `tests/fixtures/freeze_valid.yaml`: example defect specifications for the freeze validation tests.

Files of this kind, such as the undocumented drift tasks (#44), are added to this list when they
land.
