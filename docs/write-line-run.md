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
   run's judge method and model on this run's freeze, is in the file given with `--judge-validation`. The committed one is
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

## The second run (#61, #153)

The second freeze's run takes the steps above, with the differences below. Whoever runs it takes
every step, on the lead's Bedrock account, and needs no approval: the lead decides only what
happens at the cap.

| | First run | Second run |
|---|---|---|
| Configuration | `configs/write_line_thin.yaml` | `configs/write_line_second.yaml` (#152) |
| Results | `results/thin/<date>-<short commit>.jsonl` | `results/second/<date>-<short commit>.jsonl` |
| Judge validation | `results/judge_validation/2026-10-21-4af7c61.jsonl` | its own file under `results/judge_validation/` |
| Cap | $100, the default | $80: `spending_cap: 80` |
| First-pass estimate | the pilot's answers, the default | the first run's 792 answers: `estimate_from: ../results/thin/2026-10-24-66a86cb.jsonl` |

`estimate_from` is relative to the configuration, as every path in it is. The configuration is
refused when it names no file, so `--check` catches a path written from the repo root.

### Before the first call

1. **The configuration is final.** #150 and #152 are merged, and the configuration on `main` sets
   both keys of the table above. From a clean checkout:

   ```bash
   git switch main && git pull
   grep -n "^rules:\|^runs:\|^spending_cap:\|^estimate_from:" configs/write_line_second.yaml
   uv run pytest -q
   uv run python -m warrant.write_line.run --config configs/write_line_second.yaml --check
   ```

   `--check` must report `0 problems`.
2. **The credentials:** the lead's Bedrock credentials stay in a local AWS profile, never in the
   repo, a comment or a results file. Set `AWS_PROFILE` to that profile for every command below;
   `aws sts get-caller-identity` must name the lead's account.
3. **Tell the lead on #153** before the first model call, which is the judge's validation. No
   approval is needed.
4. **The judge's validation, in its own file.** The run refuses a validation made on another
   freeze (#147), so the first run's file does not clear it. `--dry-run` prints the prompts and calls
   no model:

   ```bash
   uv run python -m warrant.write_line.validate_judge --config configs/write_line_second.yaml --dry-run
   uv run python -m warrant.write_line.validate_judge --config configs/write_line_second.yaml \
     --results results/judge_validation/<date>-<short commit>.jsonl
   ```

   - Mismatches are reported, not fixed. The $80 cap counts the validation's spend too.
   - Commit the file in its own PR whose title names #153 only and whose body says `Part of #153`:
     only the last PR closes #153. Add a section on it to `results/judge_validation/README.md`, as
     the first validation has.
   - Start the run only once that PR is merged, from an updated `main` (`git switch main && git
     pull`). Every record carries the checked-out commit, so a branch's commit would be recorded.
5. **Keep the process alive,** as in step 6 above.

### Start

```bash
caffeinate -i uv run python -m warrant.write_line.run --config configs/write_line_second.yaml \
  --results results/second/<date>-<short commit>.jsonl \
  --judge-validation results/judge_validation/<file>.jsonl
```

From this call on, the configuration is not edited (ADR 0011). The run is estimated at about $40
against the $80 cap (#61), and at about four hours. The first run took 3 hours 55 minutes:
- about 2.5 minutes per claim-writing sample;
- about a minute per judgement record;
- about 6 seconds per answer.

**The first-pass threshold.** The estimate covers the first pass's answers, the number of questions
times the eight rules, at the first run's mean cost per answer, about $0.039. The run pauses if the
first pass cost more than twice its estimate. At 30 questions, that is 240 answers, an estimate of
about $9.37, and a pause above about $18.75. The pause prints both figures.

The run prints its run id only when it stops or completes. While it runs, the id is in the results
file's start record:

```bash
python3 -c "import json, sys; print(next(r['run_id'] for r in map(json.loads, open(sys.argv[1])) if r['record'] == 'start'))" results/second/<file>.jsonl
```

### When it stops

As for the first run, except at these two stops:
- **The first-pass pause:** post the first pass's cost on #153, then resume with
  `--approve-first-pass` added. No approval is needed.
- **The cap:** the next call could pass $80. Do not raise the cap; stop and tell the lead on #153.
  The cap is part of the configuration, which is frozen (ADR 0011), so the lead decides what
  happens next.

### As soon as judging is done: the blind audit sheet (#155)

Judging is done when the results file holds 8 `store` records. Then build the sheet:

```bash
mkdir -p results/second/audit
uv run python -m warrant.write_line.audit sheet --config configs/write_line_second.yaml \
  --results results/second/<file>.jsonl --sheet results/second/audit/<date>-sheet.csv \
  --key <key.json, outside the repo> --run-id <run id>
```

- **Commit the sheet alone,** in its own PR whose title and body name no defect, table or reading,
  and whose body says `Part of #153`. Commit it from a second worktree, so that the run's checkout
  stays on `main` for any resume, since every record carries the checked-out commit:

  ```bash
  git worktree add -b 153-sheet ../warrant-sheet origin/main
  mkdir -p ../warrant-sheet/results/second/audit
  cp results/second/audit/<date>-sheet.csv ../warrant-sheet/results/second/audit/
  ```

- **Post a direct link to it on #155,** with the path for the filled copy:
  `results/second/audit/<date>-sheet-filled.csv`.
- **Keep the key outside the repo,** and share it with no one until the audit's labels are in.

### After the run

Everything else stays local until the auditor's labels are in, since the stores and scores hint at
the judge's labels. Share the results file only with #154's owner, who runs the summary on it, and
outside the repo and GitHub. Once the labels are in:
1. **Compute the audit's agreement:**

   ```bash
   uv run python -m warrant.write_line.audit agreement --results results/second/<file>.jsonl \
     --sheet results/second/audit/<date>-sheet-filled.csv --key <key.json> \
     --auditor <auditor's GitHub login> --out results/second/audit/<date>-audit.jsonl
   ```
2. **In one PR, whose body says `Closes #153`, commit:**
   - the results file with a README, as `results/thin/` has;
   - the key, as `results/second/audit/<date>-key.json`;
   - the audit records the agreement wrote;
   - the run's summary (#154).
3. **Post the dates on #61:**
   - when the first complete pass finished, the latest run-0 answer of the run's first run id:

     ```bash
     python3 -c "import json, sys; rs = [json.loads(l) for l in open(sys.argv[1])]; first = next(r['run_id'] for r in rs if r['record'] == 'start'); print(max(r['timestamp'] for r in rs if r['record'] == 'answer' and r['run'] == 0 and r['run_id'] == first))" results/second/<file>.jsonl
     ```
   - when all three runs finished: the `complete` record's timestamp.

   Post the dates only, with no design or results, on #26.
4. **The spend is not compared with the Bedrock bill,** which the lead cannot read (#54). The
   recorded spend, the tokens at Anthropic's list price, is reported as unconfirmed.
