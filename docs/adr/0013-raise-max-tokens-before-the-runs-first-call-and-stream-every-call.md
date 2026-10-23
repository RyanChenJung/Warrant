# Raise max_tokens to 64,000 before the run's first call, and stream every call

Decided by the lead on 2026-10-22, before the full run's (#54) first model call. It departs from
the freeze. Under `global.claim_writing.sampling`, effort, thinking and max_tokens were fixed before
the first model call on the freeze's defects, which was the pilot (#49): effort high, thinking at
the model's default (adaptive) and max_tokens 16,000. The judge uses the same settings
(`global.judge.settings`). This amends ADR 0011, whose run configuration now holds the pilot's model
settings except max_tokens, and the lead's decision of 2026-10-20 on #26 ("max_tokens 16000,
headroom so that thinking is not cut off"), for the full run.

**What changes.**
- **max_tokens:** it is raised from 16,000 to 64,000 in the full run's configuration
  (`configs/write_line_thin.yaml`, in PR #122 before it merges). That model block is shared by claim
  writing, the judge and the answers.
- **What stays as frozen:** effort (high) and thinking (the model's default). The pilot's
  configuration stays as committed, since its SHA-256 is in every pilot record.
- **Streaming:** every call is streamed. The SDK refuses a request that is not streamed when its
  max_tokens could take more than ten minutes, which is about 21,000 tokens.

**Why.**
- **The test call** (`results/claim_writing_probe/`). One claim-writing call used the committed
  prompt, its `confident` variant and the frozen settings, on a release database outside the study
  (`robot`; neither line uses it). It used 15,566 of the 16,000 output tokens. About 5,400 of them
  were the answer's text, and the rest was thinking.
- **The run's prompts are as long or longer.** Counting the system prompt and the message, its
  claim-writing prompt runs about 7 percent longer than robot's on crypto and about as long on
  alien. Most of it is the battery's findings.
- **The output varies.** The output's length follows how many claims the agent writes and how long
  it thinks, and the run draws 40 samples at the model's default sampling, so one call at 97 percent
  of the cap leaves no room for the rest.
- **What a call at the cap does.** It stops with stop reason max_tokens and an invalid answer, and
  it is retried once.
  - A failed sample 1 stops the run. A resume draws it again, most likely into the same cap, and
    the configuration can no longer change once its first call is made (ADR 0011).
  - A failed sample from 2 to 10 counts as disagreeing. It would push that database's slots down
    the confidence ranking through a truncated output, not through the agent's uncertainty, and
    that would bias the confirmatory test.

**Why this does not fit the study to its results.**
- **The model does not see the cap.** max_tokens is a ceiling, not part of the prompt, so a call
  that stays below it is unchanged.
- **No result of the run informed it.** The decision comes before the run's first call, from a call
  on a database outside the freeze's, when no result of the run exists. The earlier calls on the
  freeze's defects, the pilot (#49) and the judge's validation, inform it only through their token
  counts.
- **The other operations stay far below either cap.** The pilot's largest answer used 4,411 output
  tokens, and the judge's calls use about 160.

## Considered Options

- **Keep 16,000.** Rejected, for the two failure modes above.
- **21,000, the most a request that is not streamed allows.** Rejected: it raises the cap by only
  31 percent, while one call already used 97 percent of the old one.
- **Lower the effort, so the model thinks less.** Rejected: unlike the cap, effort changes what the
  model does, and it is the frozen setting most likely to matter.

## Consequences

- **In the run's configuration:** PR #122 sets `max_tokens: 64000` before it merges. Its header no
  longer calls the model block the pilot's, and its test compares the model block with the pilot's
  except max_tokens, which it pins at 64,000.
- **In the write-up:** it discloses the change and the test call behind it (#54). The test call
  cost $0.21 at list price, outside the run's cap.
- **In the code:** the Claude answer agent, judge and claim writer stream their calls.
  - An error event inside a stream arrives with HTTP status 200, so its type decides whether it is
    retried.
  - The SDK retries only the request that opens a stream. So a transient failure inside one, an
    error event or a lost connection, is retried with the SDK's count and backoff, as it was when
    it came back as a failed response.
