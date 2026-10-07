# Warrant

Which statements about a dataset an AI agent may write into its own knowledge store, and which need
a person, decided by whether the data can settle them.

## Language

**Claim**:
A natural-language statement about a dataset that an agent's knowledge store holds or could hold,
such as "this export only contains closed work orders". It can be true or false; who may write it is
what the project allocates.
_Avoid_: fact, knowledge item, belief, memory entry

**Claim kind**:
A class of claims that say the same sort of thing about a dataset, such as what a table covers or
what one row represents. Results are reported per claim kind.
_Avoid_: defect type, category, knowledge type

**Probe question**:
A question whose correct answer depends on whether a given claim is known, used to measure what the
claim is worth. One claim can have many probe questions.
_Avoid_: test question, query

**Injected defect**:
A deliberate, recorded change to a clean database that makes a known claim true. It is a way to
produce claims whose truth is known, not a unit of analysis.
_Avoid_: trap, bug, corruption
