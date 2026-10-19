# Predictions

The predicted outcomes under the baseline battery (#37) land here, computed with no model call and
committed and pushed before the first agent call on the injected copies. Files here hold data
derived from LiveSQLBench-Base-Lite and are licensed under CC BY-SA 4.0
([LICENSE-DATA](../LICENSE-DATA)).

## How to predict

After the injection record of the build is committed (see [freeze/README.md](../freeze/README.md)):

```bash
uv run python -m warrant.write_line.predict --freeze freeze/<file>.yaml --injection-record injections/<file>.json
```

The command reads the copies the build left in `<data dir>/injections/<commit>/` and refuses an
injection record whose outcome is not `built` or that is of another freeze. It commits nothing:
open a PR with only what it wrote here.

## What is here

- `<commit>-<freeze>.json`: the commit and freeze of the build, the battery settings (with the
  frozen per-kind combination rule, word for word), each claim's predicted outcome with every
  reading's database and output hashes, each claim kind's prediction and each defect's bridge
  prediction.
- `<commit>-<freeze>/<content hash>.jsonl`: the normalised battery output of each distinct reading
  database, named by the database's content hash.
