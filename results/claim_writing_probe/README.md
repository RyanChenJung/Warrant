# A claim-writing call outside the study (ADR 0013)

`2026-10-23-robot.json` holds one claim-writing call, made before the full run (#54) to check the
write-claims operation's format and output length.

- **What it ran:** the committed prompt (`WRITE_CLAIMS_PROMPT_VERSION` 1, the `confident` variant)
  with the settings frozen before the pilot: `anthropic.claude-sonnet-5` on Amazon Bedrock in
  us-east-1, effort high, thinking at the model's default, max_tokens 16000, and two attempts.
- **Where:** the clean `robot` database of the release (revision `0664a2f`), which neither line uses.
  It had no business terms, and the baseline battery ran with the freeze's settings.
- **When:** on 2026-10-23 at about 00:26 UTC, for 137 seconds. It ran from a scratch copy of `main`
  at `b8efce1`, merged with PR #122's branch for its configuration's model block, which is the
  pilot's.

| | Result |
|---|---|
| Calls | 1, with no failure |
| Claims | 32, all with a confidence and cited findings (3 coverage, 10 grain, 19 value meaning) |
| Tokens | 27,449 input and 15,566 output, about 5,400 of them the answer's text and the rest thinking |
| Cost | $0.21 at Anthropic's list price, outside the run's $100 cap |

The output used 97 percent of max_tokens. Counting the system prompt and the message, the run's own
claim-writing prompts are about as long or longer: 54,208 characters on robot, 58,209 on crypto and
53,451 on alien (`prompt_chars`). So ADR 0013 raises max_tokens to 64,000 before the run's first
call.

The file holds data derived from LiveSQLBench-Base-Lite (CC BY-SA 4.0, see `LICENSE-DATA`): robot's
table and column names and the claims about them.
