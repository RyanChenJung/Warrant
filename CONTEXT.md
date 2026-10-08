# Warrant

Which statements about a dataset an AI agent may write into its own knowledge store, and which need
a person, decided by whether the data can settle them.

## Language

### Claims

**Claim**:
A natural-language statement about a dataset that an agent's knowledge store holds or could hold,
such as "this export only contains closed work orders". It can be true or false; who may write it is
what the project allocates.
_Avoid_: fact, knowledge item, belief, memory entry

**Claim kind**:
A class of claims that say the same sort of thing about a dataset. There are five: coverage, grain,
code meaning, column formula and term boundary. Results are reported per claim kind.
_Avoid_: defect type, category, knowledge type

**Coverage**:
The claim kind about what population a table was cut from and what it silently omits, such as "this
export only contains closed work orders".
_Avoid_: scope, completeness

**Grain**:
The claim kind about what one row counts as, such as "a row may be a sub-task; a work order means the
parent".
_Avoid_: row unit, granularity, row meaning

**Code meaning**:
The claim kind about what a stored value stands for, such as "'+' means the molecule is carcinogenic".
_Avoid_: value mapping, value illustration

**Column formula**:
The claim kind about which arithmetic relation between columns a business quantity names, such as
which cost components make up a total.
_Avoid_: derived metric, calculation knowledge

**Term boundary**:
The claim kind about what a business term includes, as an extension or a threshold, such as
"domestic includes Canada" or what counts as a large order.
_Avoid_: term extension, business definition, threshold

**Reference claim**:
The claim recorded when a defect is injected, in the words a knowledgeable person would use. It
contains only what that person knows without querying the data: no counts, ratios, SQL or filter
conditions, though it may name fields and codes a person would naturally mention.
_Avoid_: gold sentence, human sentence, oracle, injector log

**Provisional claim**:
A claim the agent writes although the check battery did not settle it, because the agent is highly
confident in it; it is marked as not confirmed by a person.
_Avoid_: unverified claim, tentative claim, guess

### Allocation

**Allocation rule**:
A rule that decides, for each claim, who may write it into the knowledge store: the agent, a person,
or both. The project compares allocation rules across claim kinds by answer accuracy and by how
often a person is asked.
_Avoid_: guideline, policy, routing rule

**Check battery**:
A fixed, recorded set of checks run against a database, frozen before any result is scored. Whether
the data can settle a claim is always stated relative to a named battery.
_Avoid_: checker, detector, toolbox, test suite

**Documentation**:
Written descriptions of a dataset the agent may read, such as column and value descriptions or a
glossary. Documentation can propose a claim but not settle it: the agent writes a claim taken from
documentation only if the check battery finds nothing in the data that contradicts it, cites the
source, and leaves contradicted claims to a person.
_Avoid_: data dictionary, metadata, docs

**Settled**:
A claim is settled under a check battery when the battery's output establishes it and rules out the
competing readings of the data. "Not settled" means only that this battery failed, not that no check
could succeed.
_Avoid_: decided, proven, detected, resolved

### Measurement

**Injected defect**:
A deliberate, recorded change to a clean database, or a stipulated convention, that makes a known
claim true. Term-boundary claims usually need only the convention, not a data change. It is a way to
produce claims whose truth is known, not a unit of analysis.
_Avoid_: trap, bug, corruption

**Stale documentation**:
Documentation that no longer matches the data, produced on purpose by injecting a defect into the
data and leaving its documentation unchanged.
_Avoid_: outdated docs, documentation drift

**Probe question**:
A question whose correct answer depends on whether a given claim is known, used to measure what the
claim is worth. One claim can have many probe questions.
_Avoid_: test question, query

**Correct refusal**:
A response to a probe question the data cannot answer that says what is missing and offers what can
be answered instead. A bare "cannot answer" does not count.
_Avoid_: abstention, decline

**Over-refusal**:
A refusal of a probe question the data can answer.
_Avoid_: false refusal, wrong abstention

**Clarification request**:
A response that asks the user a question instead of answering. It is reported separately and not
scored as right or wrong, because no simulated user answers it.
_Avoid_: follow-up, counter-question
