# Freeze

The write-line freeze (#34) lands here: the freeze file, with the defect specifications and the
global part, and the judge's rubric prompt. No defect is injected before the freeze commit is on the
public remote (ADR 0007). Files here hold data derived from LiveSQLBench-Base-Lite and are licensed
under CC BY-SA 4.0 ([LICENSE-DATA](../LICENSE-DATA)).

## How to inject

The order is the evidence (ADR 0007): a reader checks that the freeze commit reached GitHub before
the first commit that records an injection. Agreed on #36:

1. **Merge the freeze PR** into `main` on GitHub.
2. **Pull `main`** and stay on it, with a clean working tree: no tracked file may differ from `HEAD`,
   and `freeze/` may hold no untracked or ignored file (delete a stray `.DS_Store`; remove a draft
   kept in `.git/info/exclude`).
3. **Fetch the release** if it is not in the data directory yet: `uv run python -m warrant.data.fetch`.
4. **Run the command from `main`:**

   ```
   uv run python -m warrant.defects.build --freeze freeze/<file>.yaml
   ```

   It refuses unless the freeze file is committed and unchanged, the working tree is clean, and
   `HEAD` is on `origin/main` after a fetch. It builds the copies in the data directory, never in the
   repo, and writes the injection record to `injections/<commit>-<freeze>.json`. It commits nothing.
   A run that started injecting always leaves a record, with its outcome (`built`, `failed` or
   `drift_type_mismatch`); commit it whatever the outcome.
5. **Open a PR with only the record** and merge it as soon as CI passes.

Nothing under `freeze/` or `warrant/battery/` changes between the run and that merge: a reader dates
the injection by the record's commit, so a change merged in between would look as if it came first.
