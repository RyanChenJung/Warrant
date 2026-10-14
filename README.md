# Warrant

**Who may write what an AI analyst believes about your data.**

Research code and experiments on memory governance for AI agents that answer
questions over company data: which claims about a dataset automated checks can
settle on their own, which ones need a person, and whether that line moves when
the checks improve. Terms are defined in [CONTEXT.md](CONTEXT.md); decisions are
recorded in [docs/adr/](docs/adr/).

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
- `drift_tasks/`: the maintenance line's documented drift tasks, with edited knowledge-base entries
  (#43).
- `tests/fixtures/freeze_valid.yaml`: example defect specifications for the freeze validation tests.

Files of this kind, such as the undocumented drift tasks (#44), are added to this list when they
land.
