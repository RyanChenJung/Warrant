# Reference claims contain only what a person knows without querying the data

A reference claim that carries the injector's counts, filter conditions or SQL hands the agent the
answer and inflates the person's contribution, which is the headline result. Reference claims are
therefore written in a knowledgeable person's words: they may name fields and codes a person would
naturally mention, but contain no counts, ratios, SQL or filter conditions, and a sentence with
digits, SQL keywords or comparison operators is rejected automatically before it is used.

## Considered Options

- **Business language only, no field or code names.** Rejected: value-meaning claims such as "'+'
  means the molecule is carcinogenic" cannot be stated without naming the code.
- **No restriction, e.g. reusing the injection log.** Rejected: "deleted 40,312 rows where status is
  not CLOSE" lets the agent copy the answer instead of looking, filtering and counting.

## Consequences

The agent still has to query the data after reading a reference claim, so "everything from a person"
is a ceiling on what a person's knowledge is worth, not a lookup of the answer.
