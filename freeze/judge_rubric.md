# Judge rubric (write line, #34)

<!--
The judge operation sends the prompt below until it has three valid answers per slot claim
(global.judge.valid_call in write_line.yaml), with no sampling parameter (the model rejects
non-default ones), and combines them as global.judge.combination says. The placeholders are filled
the same way each time: {claim_kind} and {subject} from the slot, {claim} with the claim's text, and
{readings} with one line per reading of the slot, "A. <statement>", "B. <statement>" and so on, in
the slot's reading order (global.judge.reading_order). The letters map back to reading ids outside
the prompt, so the prompt shows neither the ids, the forms nor the holds flags.

It has not been tried on any model. Trying it on the defects' claims and then changing it would tune
the validation that round 3 on #34 says is reported, not fixed.
-->

## Prompt

You judge one claim about a database against several readings. Each reading is one possible
account of how things are. You are not told which reading is true, and you must not guess: judge
the claim against each reading on its own, as if that reading were how things are.

The claim is about {subject} (claim kind: {claim_kind}).

Claim:
{claim}

Readings:
{readings}

For each reading, answer exactly one of:

- **holds**: everything the claim says that the reading settles is true under the reading, and the
  reading settles at least one thing the claim says.
- **fails**: at least one thing the claim says is false under the reading.
- **not_addressed**: the reading settles nothing the claim says.

Rules:

1. Split the claim into the separate things it says. One false part makes the claim fail under that
   reading, even when every other part is true.
2. A part that the reading neither makes true nor makes false does not make the claim fail, and on
   its own it does not make the claim hold.
3. Take the claim at its word, as a careful analyst would read it. A quantity said to be A plus B is
   exactly A plus B, no more and no less.
4. A claim that says the same thing as a reading in other words holds under it. Judge what is said,
   not how it is worded.
5. Use only the claim and the reading. Do not use what you know about this database, its field,
   common conventions or which reading seems more likely.

Answer with JSON only, one key per reading letter, for example:
{"A": "holds", "B": "fails", "C": "not_addressed"}
