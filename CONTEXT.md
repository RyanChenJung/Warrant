# Warrant

Which statements about a dataset an AI agent may write into its own knowledge store, and which need
a person, decided by whether the data can settle them.

## Language

**Warrant**:
What licenses writing a claim into the knowledge store as known: settlement by a check battery, a
person's declaration, or documentation the data does not contradict. This is the epistemic sense the
project name uses. In a claim's record, the step from evidence to claim is called the inference rule,
not the warrant.
_Avoid_: using "warrant" for the inference rule, justification

### Claims

**Claim**:
A natural-language statement about a dataset that an agent's knowledge store holds or could hold,
such as "this export only contains closed work orders". It can be true or false; who may write it is
what the project allocates.
_Avoid_: fact, knowledge item, belief, memory entry

**Claim kind**:
A class of claims that say the same sort of thing about a dataset. There are five: coverage, grain,
value meaning, column formula and term boundary. Results are reported per claim kind. Join paths
are out of scope for now.
_Avoid_: defect type, category, knowledge type

**Coverage**:
The claim kind about what population a table was cut from, what it silently omits, and what data
does not exist anywhere, such as "this export only contains closed work orders".
_Avoid_: scope, completeness

**Grain**:
The claim kind about what one row counts as, such as "a row may be a sub-task; a work order means the
parent".
_Avoid_: row unit, granularity, row meaning

**Value meaning**:
The claim kind about what a stored value stands for, including codes, units and the direction of an
ordinal scale, such as "'+' means the molecule is carcinogenic" or "priority 1 is the most urgent".
_Avoid_: code meaning, value mapping, value illustration, field semantics

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

**Authoritative record**:
Documentation issued by whoever sets a convention, such as a regulation or a glossary with a named
owner and date, treated as that owner's declaration. Column descriptions written by others are
ordinary documentation, not authoritative records.
_Avoid_: official docs, source of truth

**Baseline battery**:
The weaker check battery: detectors that existed before this project's defects were designed, used
with their logic unchanged.
_Avoid_: level 1, basic checks

**Extended battery**:
The baseline battery plus cross-table checks, frozen before any defect is injected. Comparing the
two shows whether the line between agent and person moves when the checks get stronger.
_Avoid_: level 2, advanced checks, full battery

**Documentation**:
Written descriptions of a dataset the agent may read, such as column and value descriptions or a
glossary. Documentation can propose a claim but not settle it: the agent writes a claim taken from
documentation only if the check battery finds nothing in the data that contradicts it, cites the
source, and leaves contradicted claims to a person. Documentation is read when claims are written,
not when probe questions are answered.
_Avoid_: data dictionary, metadata, docs

**Reading**:
One competing interpretation of what the data means for a claim, such as "'+' means carcinogenic"
against "'+' means not carcinogenic".
_Avoid_: interpretation, hypothesis, alternative

**Reading set**:
All readings of a claim, written down when the defect is injected and frozen together with the check
batteries.
_Avoid_: candidate set, hypothesis space

**Settled**:
A claim is settled under a check battery when it holds in every reading of its reading set that the
battery cannot tell apart from the true one. "Not settled" means only that this battery failed, not
that no check could succeed. Readings that would leave the database identical can never be told
apart by any battery.
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

**Person's contribution**:
For a claim kind, answer accuracy when every claim comes from a person minus accuracy when the agent
writes every claim itself. The headline result, always reported with its uncertainty.
_Avoid_: human lift, arm 3 minus arm 2

**Agent's contribution**:
For a claim kind, answer accuracy when the agent writes every claim itself minus accuracy with an
empty knowledge store.
_Avoid_: automation lift

**Allocation outcome**:
Where a claim kind falls as measured, read from the two contributions with cutoffs fixed in advance:
agent alone, both, or person only. Outcomes from a small sample are reported as provisional.
_Avoid_: cell, verdict, category

**Predicted outcome**:
The allocation outcome a claim is expected to have under a battery, computed before any agent runs
by building the database each reading would produce and running the battery on it: agent alone if
only readings that agree on the claim survive, both if some but not all are removed, person only if
none are. The main test is whether predicted and allocation outcomes agree.
_Avoid_: expected outcome, hypothesis

**Migration**:
A claim kind whose allocation outcome changes between the baseline and the extended battery.
_Avoid_: line shift, movement

**Form familiarity**:
Whether the value or term a probe question turns on looks familiar (an everyday word with a local
meaning, such as `OPEN`) or opaque (an unfamiliar code, such as `X7`). Recorded on every probe
question.
_Avoid_: word familiarity, surface form

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
