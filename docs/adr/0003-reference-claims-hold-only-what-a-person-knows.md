# Reference claims contain only what a person knows without querying the data

A reference claim that carries the injector's counts, filter conditions or SQL hands the agent the
answer, inflates the person's contribution and so biases allocation outcomes toward a person.
Reference claims are therefore written in a knowledgeable person's words: they may name fields,
codes and term-boundary thresholds a person would naturally mention, but contain no counts, ratios,
SQL or other filter conditions, and a sentence with SQL keywords, comparison operators, or digits
outside a quoted code or a stated threshold is rejected automatically before it is used.

## Considered Options

- **Business language only, no field or code names.** Rejected: value-meaning claims such as "'+'
  means the molecule is carcinogenic" cannot be stated without naming the code.
- **No restriction, e.g. reusing the injection log.** Rejected: "deleted 1,200 rows where status is
  not CLOSED" lets the agent copy the answer instead of looking, filtering and counting.

## Consequences

The agent still has to query the data after reading a reference claim, so "everything from a person"
is a ceiling on what a person's knowledge is worth, not a lookup of the answer.
