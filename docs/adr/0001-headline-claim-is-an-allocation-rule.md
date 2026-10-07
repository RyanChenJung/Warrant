# The headline claim is an allocation rule, so we measure agent answers

The project's headline claim is an allocation rule: which kinds of statements about a dataset an
agent may write into its own knowledge store, and which need a person, decided by whether the data
can settle them. Supporting that claim requires showing that the person's sentence actually fixes
answers, so we measure agent answers to questions with and without it, not only the checks' output
against the injected ground truth.

## Considered Options

- **Capability measurement as the headline** (how much of this knowledge automated checks recover,
  scored against the injected ground truth). Safer and needs no agent in the loop, but it cannot say
  who should write what, and on its own its novelty is thin next to existing work on generating
  database documentation for text-to-SQL.
- **Benchmark or method as the headline.** Both still ship, because the injected databases and the
  frozen check battery fall out of the main experiment, but as supporting deliverables.

## Consequences

The earlier project scope form listed "no end-to-end query accuracy" as out of scope. This decision
supersedes that line.
