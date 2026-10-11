# Warrant

Repo language: English for all code, comments, commit messages, docs and issues.

## Working on a ticket

Follow `CONTRIBUTING.md`: read the issue with `gh issue view <n> --comments`, write tests for its
acceptance criteria first, put the code in the package `CONTRIBUTING.md` names for the ticket, and
run `uv run pytest` before opening a PR with `Closes #<n>`. Never inject a defect before the freeze
commit is on the public remote (ADR 0007), and never commit a database file or credentials.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues of this repo (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.

## Records

This repo is the source of truth for code, experiments, `CONTEXT.md`, ADRs and issues: record each
experiment here, so teammates see it. Findings teammates need (API or dataset facts, primary-source
investigations) go under `docs/research/`.
