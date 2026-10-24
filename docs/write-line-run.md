# Running the write line's full run (#54)

The steps for the lead, who runs the full run on the lead's Bedrock account (#26). The run's first
model call freezes its configuration (ADR 0011), so the checks below come first. Every step can be
repeated except that call.

## Before the first call

1. **The configuration is final.** PR #122 is merged, and `configs/write_line_thin.yaml` on `main`
   holds the eight rules of ADR 0012, `runs: 3` and `max_tokens: 64000` (ADR 0013).

   ```bash
   git switch main && git pull
   grep -n "^rules:\|^runs:\|max_tokens" configs/write_line_thin.yaml
   uv run pytest -q
   ```

   Run from a clean checkout. Every record carries the checked-out commit, so uncommitted changes
   would be recorded under a commit that does not hold them.
2. **The questions check:** `--check` must report `0 problems`. It makes no model call.

   ```bash
   uv run python -m warrant.write_line.run --config configs/write_line_thin.yaml --check
   ```
3. **The credentials:** `aws sts get-caller-identity` names the lead's account. The run's own first
   call is the real check.
4. **The judge's validation:** the run writes no claim until a complete validation, made with this
   run's judge method and model, is in the file given with `--judge-validation`. The committed one is
   `results/judge_validation/2026-10-21-4af7c61.jsonl`. The $100 cap counts its spend too.
5. **One results file for the whole run:** `results/thin/<date>-<short commit>.jsonl`, as
   `results/pilot/` holds the pilot's. Every invocation of the run uses this same file: the cap, the
   resume and the summary read it.
6. **Keep the process alive:**
   - Keep the machine awake: `caffeinate -i` on macOS.
   - Run it in tmux, or under `nohup` if a logout must not stop it.
   - Ctrl-C, SIGTERM or a closed terminal stops the run cleanly, its records kept, and a resume
     goes on from there.

## Start

```bash
caffeinate -i uv run python -m warrant.write_line.run --config configs/write_line_thin.yaml \
  --results results/thin/<date>-<short commit>.jsonl \
  --judge-validation results/judge_validation/2026-10-21-4af7c61.jsonl
```

From this call on, `configs/write_line_thin.yaml` is not edited (ADR 0011). The run goes through
these steps, estimated at about $43 in all against the $100 cap:

| Step | Calls | About | Records |
|---|---|---|---|
| Claim writing | 40: 2 variants × 2 databases × 10 samples | 80 minutes | `sample` |
| Judging | about 200 | 15 minutes | `judgement` |
| Stores | none | seconds | 8 `store` |
| First pass | 264 answers | 65 minutes | `answer` |
| Runs 2 and 3 | 528 answers | 2 hours 10 minutes | `answer`, then `complete` |

The times come from three sources:
- the test calls: about 2 minutes per claim-writing call (`results/claim_writing_probe/`);
- the judge's validation: about 18 calls a minute;
- the pilot: about 15 seconds per answer.

To watch the progress:

```bash
python3 -c "import json, sys, collections; print(dict(collections.Counter(json.loads(l)['record'] for l in open(sys.argv[1]))))" results/thin/<file>.jsonl
```

## When it stops

A stop keeps every record and pays for nothing twice. The run prints its run id, and a resume makes
only the calls still missing:

```bash
caffeinate -i uv run python -m warrant.write_line.run --config configs/write_line_thin.yaml \
  --results results/thin/<file>.jsonl --judge-validation results/judge_validation/2026-10-21-4af7c61.jsonl \
  --run-id <run id>
```

**Exit 3, stopped on purpose.** Resume as above, except where the lead must decide first:
- **The cap:** the next call could pass $100. Raising the cap is the lead's decision.
- **The first-pass pause:** the first pass cost more than twice its estimate, about $10.70, so more
  than about $21.40. The lead looks at its cost, then resumes with `--approve-first-pass` added.
- **A failed sample 1:** the resume draws it again.

**Exit 2, refused before any call.** Fix the cause, then run again:
- **A misconfiguration.**
- **The judge's validation does not clear claim writing.**
- **A run of this configuration is already in the results file.** Resume it with `--run-id`.
  `--new-run` starts another, but only on purpose: it pays for everything again, and the summary
  uses the first complete run.

**Any other error.** A platform error that is not transient prints a traceback, and its note names
the run id. Resume with `--run-id` once the cause is fixed.

**An interrupt:** Ctrl-C, SIGTERM or a closed terminal. Resume with `--run-id`.

Never run two invocations on the same results file at once: nothing locks it.

## As soon as judging is done: the blind audit sheet (#123)

Judging is done when the results file holds 8 `store` records. Then build the sheet, before the
answers are done:

```bash
uv run python -m warrant.write_line.audit sheet --config configs/write_line_thin.yaml \
  --results results/thin/<file>.jsonl --sheet <sheet.csv> --key <key.json> --run-id <run id>
```

- **The sheet goes to Juan.** It covers the `confident` variant's claims only.
- **The key stays with the lead**, out of the repo, until the audit is in.
- **The do-not-look list on #123 still holds for Juan**, the results file included.

## After the run

1. **Record the dates on #54:**
   - when the first complete pass finished, and whether it met 2026-11-16 23:59 America/Chicago,
     which decides the second freeze (ADR 0011, #61). Its time is the latest run-0 answer of the
     run's first run id:

     ```bash
     python3 -c "import json, sys; rs = [json.loads(l) for l in open(sys.argv[1])]; first = next(r['run_id'] for r in rs if r['record'] == 'start'); print(max(r['timestamp'] for r in rs if r['record'] == 'answer' and r['run'] == 0 and r['run_id'] == first))" results/thin/<file>.jsonl
     ```
   - when all three runs finished: the `complete` record's timestamp.
2. **Commit the results file** under `results/thin/` with a README, as `results/pilot/` has. Its
   data are derived from LiveSQLBench-Base-Lite, and the README's licence list covers `results/`.
3. **Run the summary (#53)** on the results file, and commit it in `results/thin/`.
4. **Compare the recorded spend** with the Bedrock bill.
