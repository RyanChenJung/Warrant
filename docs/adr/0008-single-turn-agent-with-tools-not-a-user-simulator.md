# The agent answers in a single turn with tools, and no user simulator is added

The agent gets one task and answers it without further turns from a user, after calling any of
the tools its condition offers: read-only SQL on the database, a lookup of current records, and
escalation to an oracle person who returns the current definition when asked. Single-turn is the
data's own setting: LiveSQLBench-Base-Lite, which both lines use (ADR 0009), is a single-turn
text-to-SQL benchmark in which each task pairs one question with one gold SQL. No user simulator is
added. A simulator that sees the gold SQL could leak a rule that changed under drift, which would
give the agent an uncontrolled channel to the new rule and corrupt the escalation measure. An
explicit escalation tool makes every contact with a person controlled and counted.

## Considered Options

- **A multi-turn setting with a user simulator, as in BIRD-Interact.** It would cover the
  interactive case, but a reply from the simulator could carry the new rule without counting as an
  escalation, so neither silent errors nor questions to a person could be measured cleanly.

## Consequences

- Results may not transfer to interactive settings, where a user's replies can reveal a changed
  rule. The paper states this as a limitation; multi-turn is future work.
- Which tools are offered is part of a condition: the maintenance line's main stored-answer
  condition offers the lookup tools without telling the agent to use them, and a no-tools condition
  is its control. The agent interface therefore takes the tool set with each request, while
  requests still never name the condition.
- Escalation is an act within answering, as CONTEXT.md defines it, not a kind of final response:
  the run still ends in one scored response, and each escalation call is logged and counted as one
  question to a person; clarification requests are a response class and are not counted as
  questions to a person. A run counts as a silent error as CONTEXT.md defines it: a wrong answer
  given without an error, a refusal, a clarification request or an escalation.
- The person the agent escalates to is an oracle; asking real people is future work.
