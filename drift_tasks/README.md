# Documented drift tasks (#43)

The maintenance line's part (1) asks whether an agent's stored knowledge goes stale when the
knowledge base changes. Each task here takes one LiveSQLBench-Base-Lite knowledge-base entry that
fixes a constant or threshold, asks a single-turn question whose answer depends on it, and gives the
entry a new version with the number changed. The database never changes: before drift the gold
answer follows the released entry, after drift the new version, so an answer that still follows the
released entry is a stale value. `config.yaml` lists the 20 tasks in draw order; validate them with

    uv run python -m warrant.maintenance.validate --config drift_tasks/config.yaml

The rules were decided with the lead on 2026-10-14 and are recorded on #43. In short:

- **Entries.** An entry on any database but crypto and alien, the write line's. The entries the
  changed one builds on are listed in the task, unchanged. Every entry that restates the same
  constant, meaning the same number in the same role for the same metric, changes with it, so the
  post-drift knowledge base never contradicts itself; each task file's header says which entries
  were changed and which were left, and why.
- **The number.** The first constant or threshold in the definition; unit conversions, identifiers
  and examples are not constants. Its new value is the old one moved by 20 percent in the drawn
  direction, rounded to the old number's decimal places (`new_value` in `warrant/maintenance/draw.py`).
  If the task then fails the checks, the other direction is tried once.
- **The question.** A single number, naming the entry's term and never the constant, asking about
  the entry itself. For a condition it counts what meets it; for a value it asks for the average,
  and if that moves by less than 5 percent in both directions, the maximum, then the minimum. No
  other entry's cut-off and no number of the authors' own is brought in.
- **The answers.** Neither state's gold result is empty or 0, and the two differ by more than the
  scorer's 5 percent tolerance (the run's tolerance is fixed by #47).

## How the entries were chosen

`uv run python -m warrant.maintenance.draw` lists every entry of the 16 databases whose definition
states a number (768) in an order drawn with seed 20261015, each with a drawn direction. Entries
were taken in that order, at most 2 per database, until 20 tasks were written. An entry was passed
over only for a reason listed in advance on #43, or because it states no constant or threshold:

- **(a)** no single-turn question that needs no clarification can be written;
- **(b)** the gold SQL needs data the database lacks;
- **(c)** both directions fail the checks (the results are too close, empty or 0).

Every task and every passed-over entry was checked by a second agent that recomputed the answers
with its own SQL and tested each reason; three tasks were corrected after that check (their file
headers say how). The 20th task came at position 55.

| Position | Database | Entry | Outcome |
|---|---|---|---|
| 1 | cross_db | 2 | No constant: the only number is the exponent -1 of a reciprocal |
| 2 | cybermarket | 26 | (c): the entry's other conditions already force APL above 117, so the count is 166 in every state |
| 3 | gaming | 40 | (c): 39 devices in every state; CGPI runs far above every version of the cut-off |
| 4 | solar | 11 | (b): the database records no panel strings, which the definition compares within |
| 5 | insider | 11 | **Task** `insider-11` |
| 6 | archeology | 31 | **Task** `archeology-31` |
| 7 | mental | 54 | (c): the constant 0.01 rounds back to 0.01 in both directions |
| 8 | disaster | 51 | **Task** `disaster-51` |
| 9 | fake | 41 | **Task** `fake-41` |
| 10 | insider | 59 | (c): the floor 1 rounds back to 1 in both directions |
| 11 | news | 35 | No constant: the 2 makes PAM the mean of two terms |
| 12 | solar | 37 | No constant: a complement and a percent conversion |
| 13 | gaming | 46 | (c): the count moves 1.5 percent down and 2.2 percent up |
| 14 | cybermarket | 31 | (c): every vendor has one market, so the average moves 0.01 percent |
| 15 | news | 9 | No constant: the numbers are examples of event positions |
| 16 | vaccine | 31 | (c): the average moves under 0.1 percent |
| 17 | virtual | 5 | **Task** `virtual-5` |
| 18 | insider | 1 | No constant: a complement and the zero point of a denominator |
| 19 | gaming | 32 | **Task** `gaming-32` |
| 20 | news | 5 | (c): the weight 1 rounds back to 1 in both directions |
| 21 | disaster | 21 | **Task** `disaster-21` |
| 22 | disaster | 26 | Not reached: disaster had 2 tasks |
| 23 | mental | 45 | **Task** `mental-45` |
| 24 | vaccine | 0 | (c): its average, sum, minimum and maximum move under 3 percent |
| 25 | cross_db | 56 | No constant: 365 converts days to years |
| 26 | virtual | 34 | **Task** `virtual-34` |
| 27 | gaming | 15 | **Task** `gaming-15` |
| 28 | cybermarket | 37 | (c): its average, sum, minimum and maximum move under 3.5 percent |
| 29 | virtual | 38 | Not reached: virtual had 2 tasks |
| 30 | disaster | 40 | Not reached: disaster had 2 tasks |
| 31 | cross_db | 10 | **Task** `cross_db-10` |
| 32 | polar | 10 | (c): the count is 0 before drift |
| 33 | news | 8 | **Task** `news-8` |
| 34 | mental | 14 | (c): TES takes only the values 0 to 3, so every version selects the same 248 patients |
| 35 | cybermarket | 12 | **Task** `cybermarket-12` |
| 36 | cybermarket | 15 | No constant: unit conversions and a complement |
| 37 | vaccine | 46 | (c): the count moves 3.3 percent down and 2.9 percent up |
| 38 | archeology | 2 | No constant: the only digit is in the column name AreaM2 |
| 39 | disaster | 41 | Not reached: disaster had 2 tasks |
| 40 | solar | 34 | (c): 137 panels before drift, 137 and 136 after |
| 41 | polar | 14 | **Task** `polar-14` |
| 42 | polar | 27 | (c): no record is below either version of the cut-off, so the count is 0 |
| 43 | fake | 55 | No constant: complements and a percent conversion |
| 44 | polar | 48 | **Task** `polar-48` |
| 45 | credit | 33 | **Task** `credit-33` |
| 46 | credit | 32 | No constant: the only number is a percent conversion |
| 47 | museum | 24 | (c): every humidity reading lies inside every version of the range |
| 48 | cybermarket | 36 | **Task** `cybermarket-36` |
| 49 | cross_db | 30 | (c): the constant 1 rounds back to 1 in both directions |
| 50 | credit | 36 | **Task** `credit-36` |
| 51 | vaccine | 56 | (b): it needs three consecutive readings per shipment; the database has one |
| 52 | gaming | 17 | Not reached: gaming had 2 tasks |
| 53 | fake | 49 | (c): NMI runs from 3.93 to 53.31, far above every version of the cut-off 0.9 |
| 54 | news | 54 | **Task** `news-54` |
| 55 | solar | 2 | **Task** `solar-2` |

Candidates were written in parallel, so three entries after position 55 were also made into valid
tasks before the count was known (mental 58, cross_db 68 and museum 10, at positions 62, 70 and 73).
They are not used, because the 20 tasks were reached first.

## Authorship and licence

The tasks were drafted with an AI coding assistant, Claude Code running Claude Opus 5.5, of the same
model family as the experiment model, as the write-line freeze also discloses; the order was drawn
by the seed, not chosen by the assistant. The knowledge-base entries, table and column names in
these files come from LiveSQLBench-Base-Lite, so this directory is derived data under CC BY-SA 4.0
(see the README and `LICENSE-DATA`).
