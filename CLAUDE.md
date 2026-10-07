# Warrant

Repo language: English for all code, comments, commit messages, docs and issues.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues of this repo (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.

## Project memory in the Obsidian vault

This repo is the source of truth for code, experiments, `CONTEXT.md`, ADRs and issues.
The author's Obsidian vault keeps a pointer note so other projects can find the current
state of this one: `Raw/00-Project-Overview/Warrant-Pointer.md` in the vault.

- Record each experiment in this repo first, so teammates see it.
- Then add a short summary note to the vault (result, decision, link back to the repo file or issue).
- Never copy an ADR or `CONTEXT.md` into the vault; link to it.
