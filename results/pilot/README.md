# The write line's minimal real-model pilot (#49)

`2026-10-20-e33ac97.jsonl` holds the 16 stored results of the pilot: one record per answer, with the
run's provenance (repo commit `e33ac97`, the SHA-256 of `configs/write_line_pilot.yaml`, the model
and the prompt version), the question, the rule, the response class and bucket, the final SQL, the
tokens and any failure. It was run on 2026-10-20 between 16:49 and 16:53 UTC with
`uv run python -m warrant.write_line.run --config configs/write_line_pilot.yaml`, from `main` at
`e33ac97`, after the questions and model settings were pushed (16:49:10 UTC; first answer 16:49:50).
The run rebuilt the databases and checked every copy's content hash against
`injections/9cfd501f2182-write_line.json` before the first agent call.

| Probe | Empty store | Everything from a person |
|---|---|---|
| orders-placed (999) | wrong (733) | wrong (733) |
| fees-charged | correct | correct |
| filled-notional | correct | correct |
| fee-per-order | correct, by another method (fees per fee record, 0.1 percent from gold) | correct |
| orders-cancelled (266) | wrong (756) | correct |
| cancelled-share | wrong | correct |
| fees-on-cancelled | wrong | correct |
| filled-notional-on-cancelled | wrong | correct |
| Accuracy | 3 of 8 (0.375) | 7 of 8 (0.875) |

Under everything from a person, the store held the reference claims of all three frozen defects,
since the runner composed one store from every defect of the freeze. So the crypto questions also
saw the alien value-meaning claim (`seeing-recode`). It is about another database, and no pilot
question touches it. From #54 on, each question gets only its own database's claims (#50).

What the records do not hold is the value each final SQL returns; the values above come from
re-executing the stored SQL on the rebuilt injected copy. The results are data derived from
LiveSQLBench-Base-Lite (table and column names in the SQL), under CC BY-SA 4.0.
