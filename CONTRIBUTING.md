# Contributing

The plan is issue #26; every piece of work is one of its tickets. Terms are defined in
[CONTEXT.md](CONTEXT.md) and decisions in [docs/adr/](docs/adr/).

## Setup

Install [uv](https://docs.astral.sh/uv/), then from the repo root:

```bash
uv sync
uv run pytest
```

`uv sync` installs Python 3.13 (the version the vendored detectors require) and the dependencies
pinned in `uv.lock`. Add a dependency with `uv add <package>` and commit `uv.lock` with it; if
`uv.lock` conflicts during a merge, take either side and run `uv lock` again.

## Working on a ticket

1. **Claim it.** Assign yourself on the issue (`gh issue edit <n> --add-assignee @me`). Start only
   when the tickets it is blocked by are closed.
2. **Branch.** `git switch -c <n>-short-name` from an up-to-date `main`.
3. **Build it.** Open Claude Code in the repo and ask it to implement issue `#<n>` against its
   acceptance criteria, tests first. Read and run what it writes; you are the author.
4. **Open a PR** with `Closes #<n>` in the description and merge it yourself once the tests pass; no
   review is needed, so we can iterate fast. Every change to `main` still goes through a PR. Merging
   closes the issue and unblocks the tickets waiting on it.
5. **Log your time.** Once a week, comment on each ticket you worked on: hours spent and which
   acceptance criteria are met. The October 17 checkpoint (#57) compares these logs with the
   estimates.

## Hard rules

- **No defect is injected into any database before the freeze commit is pushed to the public repo**
  (ADR 0007). The injection command refuses to run otherwise; do not work around it. While
  designing the freeze, a candidate defect may be tried on a scratch copy outside the data
  directory and run through the battery, never through a model; every such trial is disclosed in
  the freeze note. No model call touches a defect before the freeze commit is pushed.
- **No database file is committed.** The release and every rebuilt database live in the data
  directory, `$WARRANT_DATA_DIR` (default `~/.cache/warrant`, see `warrant/config.py`). Only tiny
  fixture databases under `tests/fixtures/` are committed.
- **No credentials are committed.** Real-model calls use Claude through the project lead's AWS
  Bedrock account: ask the lead before running any, and keep credentials in a local AWS profile or
  environment variables. The model id and region go in the configuration.
- **Tests never download anything or call a model.** They use fixtures and the scripted fake agent.

## Where code goes

| Package | What | Tickets |
|---|---|---|
| `warrant/data/` | Fetching and loading the release; the table export the battery reads | #29, #30 |
| `warrant/battery/` | The vendored Gloss detectors and the normalisation of their output | #28, #31 |
| `warrant/freeze/` | Freeze file formats and their validation command | #33 |
| `warrant/defects/` | Injection on database copies; the per-reading database builder | #27, #35, #36 |
| `warrant/agent/` | Agent interface, scripted fake agent, Claude agent, tools | #27, #38, #39 |
| `warrant/store/` | The knowledge-store format shared by both lines | #27, #50 |
| `warrant/scoring/` | Scoring and statistics shared by both lines | #40, #41 |
| `warrant/write_line/` | Write-line entry point: predictions, allocation rules, runs, summary | #27, #37, #50 to #53 |
| `warrant/maintenance/` | Maintenance-line entry point: drift tasks, conditions, escalation, summary | #42, #45 to #48 |

If a ticket needs code somewhere else, say why in the PR.

## Conventions

- **Configuration and freeze files are YAML**, committed to the repo and read with
  `yaml.safe_load`. Their schemas come from #27 (configuration) and #33 (freeze).
- **Commands are modules** with a `main(argv=None)` function, run as
  `uv run python -m warrant.<package>.<command>`, for example `python -m warrant.data.fetch`.
- **Tests** live in `tests/`, are named after the behaviour they check, and assert on what an entry
  point returns. Fixture databases and files go in `tests/fixtures/`.
- **English** for code, comments, commit messages, PRs, issues and docs. Use the terms in
  CONTEXT.md, not the alternatives it lists under _Avoid_.
