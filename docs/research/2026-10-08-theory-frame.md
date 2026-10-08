# Theoretical frame: identification under a frozen check battery

2026-10-08. Three literature sweeps (epistemology and argumentation; language, social ontology and
organisations; data provenance and decision frames in computing), a comparison of about 25 frames,
and a separate citation check. Decided in the 2026-10-08 grilling session.

## Decision

| Role | Frame | Job |
|---|---|---|
| Primary | Identification: whether the check battery can tell a claim's competing readings apart | Defines settled and the three allocation outcomes, predicts them before any agent runs, explains migration |
| Supporting | Searle's constitutive rules and declarations | Explains why readings no check can separate need a person: the person authors the rule, which is different from being more accurate |
| Record format | Toulmin's layout, with Freeman's empirical vs institutional warrants | How each stored claim records its justification, and how a "both" claim is shown to a person |

Toulmin is not the primary frame. It describes the parts of an argument but has no rule for
evaluating one, so it cannot say when a rebuttal counts as ruled out (and so cannot define settled),
cannot predict outcomes before the experiment, and cannot say which claims a stronger battery moves.

## The primary frame

The same structure exists in three fields, which is why it reads across the candidate audiences:

- databases: certain answers over a set of possible databases (Libkin 2016; Abiteboul, Kanellakis &
  Grahne 1991) and completeness statements that cannot be verified from the database itself
  (Razniewski & Nutt 2011);
- econometrics and information systems: partial identification and the identification region
  (Manski 2003);
- machine learning: version-space selective classification (El-Yaniv & Wiener 2010).

Definitions below are this project's synthesis; no cited author defines them this way.

- The **readings** of a claim are its competing interpretations, written down with the reference
  claim and committed before the defect is injected, like the check batteries.
- For each reading, imagine the database that would result if it were the true one. For a pure
  convention, that database is the clean database itself.
- The battery **cannot tell two readings apart** when it produces the same output on both databases.

| Allocation outcome | Condition | Identification terms | Database terms |
|---|---|---|---|
| Agent alone (settled) | The claim holds in every reading the battery cannot tell apart from the true one | Point-identified | Certain answer |
| Both | The battery removes some readings, but those left disagree on the claim | Set-identified | - |
| Person only | The battery removes no reading | Not identified | - |

### What it predicts

- **Migration.** Readings that would leave the database identical can never be told apart, however
  strong the battery. A claim can migrate only if its remaining rivals give different databases that
  the baseline battery cannot distinguish but the extended one can.
- **Direction.** Adding checks can only remove readings, so the line moves one way: toward the agent.
- **Documentation** removes readings without data evidence, like an assumption in Manski's sense.
  Stale documentation can be caught only if the readings it removes would give a different database.
- **Provisional claims** pick one reading among those left using the agent's prior; by Manski's law
  of decreasing credibility they should be the least reliable.
- **Absence claims** ("this data exists nowhere") rest on a closed-world assumption (Reiter 1978)
  that checks inside the database cannot establish.
- **The confidence rule is a rival rule, not a weaker version of this one.** El-Yaniv & Wiener
  show that, in the noise-free realizable setting, the optimal selection function "is not obtained by
  thresholding soft classification values".

### Testing the prediction before any agent runs

For each claim and each of its readings, build the corresponding database and run both batteries.
This gives a predicted outcome for every claim under each battery, and a predicted migration, with no
agent involved. The experiment then tests whether the measured allocation outcome matches it. Two
comparisons decide between this rule and its rivals:

- **Off-diagonal claims**: easy but unsettled (a familiar-word term boundary) and hard but settled
  (grain resolved by a cross-table check). The confidence rule and difficulty-based rules disagree with
  settlement exactly here.
- **Stronger model, battery fixed**: the confidence rule and learning to defer predict more claims
  written by the agent alone; identification predicts the same allocation. Issue #5 (open-weights
  replication) can supply the second model.

### Predicted outcome by claim kind (synthesis; the matrix computes it per claim)

| Claim kind | Rivals that leave the database identical | Default prediction | Migrates only if |
|---|---|---|---|
| Coverage | Which population was cut, seen from one table; "absent anywhere" | Both | Another table holds the uncut population. "Absent anywhere": never |
| Grain | Which unit the term names | Both | Another table counts at a single unit |
| Value meaning | Relabellings (swapped codes, reversed scale) | Person only | Another field correlates with the code |
| Column formula | Which identity the business term names | Agent alone for which identity holds; both for the naming | Another table reports the named quantity |
| Term boundary | All readings, unless the classification is stored | Person only | A stored flag, or an aggregate computed under the convention, exists |

## Supporting frame: Searle

- The readings that no check can separate differ on a rule of the form "X counts as Y in C"
  (Searle 1995).
- A declaration makes such a rule true: the authorised utterance makes the world match (Searle 1976).
- For a convention, "expert accuracy" is not a variable. Learning to defer and Fügener, Walzner &
  Gupta (2026) allocate by who is more likely to be right about an independent fact; here the person
  is the author, not a better predictor. This is the answer to both foils.
- Read "brute" relationally (Anscombe 1958): a fact is brute relative to a description. This answers
  the objection that every database row is itself institutional.
- Searle's frame is used in IS conceptual modelling (Eriksson, Johannesson & Bergholtz 2018) and in
  AI and law counts-as logics (Jones & Sergot 1996).

## Record format: Toulmin

| Slot | A data-part claim ("every row has status CLOSED") | A convention-part claim ("domestic includes Canada") |
|---|---|---|
| Claim | The claim | The claim; its content is itself a counts-as rule |
| Grounds | Battery output, plus the rows that witness it | Battery output, usually nothing that bears on it |
| Inference rule (Toulmin's warrant) | The detector's rule (Freeman: empirical) | The counts-as rule (Freeman: institutional) |
| Backing | The battery's frozen record | A declaration by a person or an authoritative record |
| Rebuttal | The readings not yet removed | Usually all readings |
| Qualifier | Settled, person-confirmed, documentation not contradicted, or provisional | Same |

For a convention-part claim the claim and its inference rule are the same counts-as rule; the person
authors it, and the declaration is recorded as backing.
Because every slot is filled from battery logs and readings written down in advance, the usual NLP
objection that Toulmin slots cannot be annotated reliably (Habernal & Gurevych 2017 dropped warrants;
Niven & Kao 2019) does not apply.

## Comparison (main candidates; scores 1-5 are the comparison's judgement, higher is better)

| Frame | Three outcomes | Predicts before the experiment | Migration | Role |
|---|---|---|---|---|
| Identification (Manski; certain answers; El-Yaniv & Wiener) | 5 | 4 | 5 | Primary |
| Searle: constitutive rules, declarations | 3 | 3 | 4 | Supporting |
| Epstein: grounding vs anchoring | 4 | 4 | 5 | Alternative to Searle, only for a philosophy venue |
| Daft & Lengel: uncertainty vs equivocality | 3 | 3 | 3 | Cite for question form |
| Toulmin + Freeman | 3 | 2 | 3 | Record format |
| Pollock / ASPIC+ / Dung | 4 | 2 | 3 | Appendix only |
| Testimony (Burge, Lackey, Goldberg) | 2 | 2 | 2 | Cite for the documentation rule |
| FEVER / TabFact | 2 | 1 | 1 | Related work |
| Learning to defer; Fügener et al. 2026; confidence thresholding | - | - | - | Foils |

## Expected attacks

1. **"You chose the readings."** Write them down and commit them before the defect is injected;
   for robustness, add readings proposed afterwards by an independent model or person and report how
   many outcomes change.
2. **"This is just identifiability."** Concede it. The contribution is using it as the rule for what
   an agent may write into its own store, the head-to-head tests against confidence and relative
   accuracy, and per-kind migration.
3. **"The allocation outcome is accuracy-based, so this is relative accuracy."** The rule uses no
   accuracy labels; accuracy only evaluates which rule predicts the measured outcome better.
4. **"The true reading may not be among those written down."** State this assumption; treat absence
   claims as resting on a closed-world assumption.

## Positioning (decided 2026-10-08)

For the abstract:

> Prior work assigns a task to the human or the AI by who is more likely to be right. We assign the
> writing of a claim by whether the data can tell its readings apart; where it cannot, the person is
> the claim's author, not a better predictor.

For the introduction, against the closest neighbour (Qi, Xu & Li 2026, arXiv 2607.02579):

> Closest to our setting, GovMem gates an agent's memory writes by how independent the supporting
> traces are; we gate them by what checks on the data can rule out, and test that rule against model
> confidence for each kind of claim.

One line each in related work:

- **Learning to defer** decides who answers each query; Warrant decides who may write each claim.
- **Huang et al. 2023; Wretblad et al. 2024** show that documentation helps; Warrant asks who may
  write it.
- **BIRD-Interact** fixes in advance which knowledge must be asked; Warrant measures it.

## Decisions that followed (2026-10-08)

- **Names**: reading, reading set, predicted outcome (see CONTEXT.md).
- **"Warrant"** in the project name is the epistemic sense (Plantinga 1993): what licenses writing a
  claim as known. Toulmin's warrant slot is called the inference rule.
- **Documentation for conventions.** "The data does not contradict it" is vacuous for the convention
  part of a claim, because its readings leave the database identical: a stale glossary saying
  "domestic means the US only" can never be caught by checks. The experiment keeps the uniform
  documentation rule, which turns this into a prediction: stale documentation is caught for coverage,
  grain and whether a column formula's identity holds, but not for value meaning, term boundary or
  which quantity a business term names. The thesis then recommends, with that evidence, that a person
  confirm the convention part of documentation-backed claims unless the source is an authoritative
  record
  (a regulation, or a glossary with a named owner and date). Treating written rules as standing
  declarations (Searle 2010) rests only on a review so far; read the primary text before relying on
  it.

## Citation notes from the check

- Manski's own term is "identification region"; "identified set" is later usage.
- Trace "certain answers" to Abiteboul, Kanellakis & Grahne (1991) or Libkin (2016), not to
  Imieliński & Lipski (1984), who give the possible-worlds semantics.
- El-Yaniv & Wiener's result holds for noise-free, realizable learning only.
- Reiter treats the closed-world assumption as an assumption that holds when information is
  complete; calling it a convention is this project's gloss.
- Freeman's four warrant types are confirmed from the abstract; that institutional warrants rest on
  constitutive rules still needs the full text.
- Elmasri & Navathe's statement that functional dependencies cannot be inferred from an instance:
  confirm the edition (likely 6th ed., §15.2.1) in a real copy.

## References

- Abedjan, Z., Golab, L., & Naumann, F. (2015). Profiling relational data: A survey. *The VLDB Journal* 24(4), 557-581. https://doi.org/10.1007/s00778-015-0389-y
- Abiteboul, S., Kanellakis, P., & Grahne, G. (1991). On the representation and querying of sets of possible worlds. *Theoretical Computer Science* 78, 159-187.
- Anscombe, G. E. M. (1958). On brute facts. *Analysis* 18(3), 69-72. https://doi.org/10.1093/analys/18.3.69
- El-Yaniv, R., & Wiener, Y. (2010). On the foundations of noise-free selective classification. *JMLR* 11, 1605-1641. https://jmlr.org/papers/v11/el-yaniv10a.html
- Eriksson, O., Johannesson, P., & Bergholtz, M. (2018). Institutional ontology for conceptual modeling. *Journal of Information Technology* 33(2), 105-123. https://doi.org/10.1057/s41265-018-0053-2
- Freeman, J. B. (2005). Systematizing Toulmin's warrants: An epistemic approach. *Argumentation* 19(3), 331-346. https://doi.org/10.1007/s10503-005-4420-0
- Fügener, A., Walzner, D. D., & Gupta, A. (2026). Roles of artificial intelligence in collaboration with humans. *Management Science* 72(1), 538-557. https://doi.org/10.1287/mnsc.2024.05684
- Habernal, I., & Gurevych, I. (2017). Argumentation mining in user-generated web discourse. *Computational Linguistics* 43(1), 125-179. https://doi.org/10.1162/COLI_a_00276
- Jones, A. J. I., & Sergot, M. (1996). A formal characterisation of institutionalised power. *Logic Journal of the IGPL* 4(3), 427-443. https://doi.org/10.1093/jigpal/4.3.427
- Libkin, L. (2016). Certain answers as objects and knowledge. *Artificial Intelligence* 232, 1-19. https://doi.org/10.1016/j.artint.2015.11.004
- Manski, C. F. (2003). *Partial Identification of Probability Distributions*. Springer. https://doi.org/10.1007/b97478
- Manski, C. F. (2010). Policy analysis with incredible certitude. NBER Working Paper 16207. https://www.nber.org/papers/w16207
- Niven, T., & Kao, H.-Y. (2019). Probing neural network comprehension of natural language arguments. ACL 2019. https://aclanthology.org/P19-1459/
- Plantinga, A. (1993). *Warrant: The Current Debate*. Oxford University Press.
- Razniewski, S., & Nutt, W. (2011). Completeness of queries over incomplete databases. *PVLDB* 4(11), 749-760. https://www.vldb.org/pvldb/vol4/p749-razniewski.pdf
- Reiter, R. (1978). On closed world data bases. In *Logic and Data Bases*, 55-76. Plenum. https://doi.org/10.1007/978-1-4684-3384-5_3
- Searle, J. R. (1976). A classification of illocutionary acts. *Language in Society* 5(1), 1-23. https://doi.org/10.1017/S0047404500006837
- Searle, J. R. (1995). *The Construction of Social Reality*. Free Press.
- Toulmin, S. E. (2003). *The Uses of Argument* (updated ed.; first published 1958). Cambridge University Press. https://doi.org/10.1017/CBO9780511840005
