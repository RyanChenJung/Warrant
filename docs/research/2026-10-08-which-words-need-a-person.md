# Which words need a person? Linguistics, social science and data semantics

2026-10-08. Three literature sweeps (linguistics; philosophy, law and organisation studies; databases
and NLP), a synthesis, and a separate citation check. Where the check narrowed a claim, the narrower
version is used here.

## Summary

- **Part of speech is a weak predictor and the wrong axis.** Word-sense studies find nouns somewhat
  easier to agree on than verbs and adjectives, but the effect is inconsistent, confounded with how
  many senses a word has, and measures disagreement among general readers. Warrant's failures are the
  opposite: every general reader picks the same reading, and the organisation means something else.
  No study reports how often a person is needed, by part of speech, in data question answering.
- **A better description of an expression has three parts:** which part of its meaning is left open,
  who fixes that part, and how familiar the word looks. A familiar word with a local meaning is the
  dangerous case: the agent is confident and does not think to ask.
- **Each existing claim kind has a linguistic counterpart** (table in section 3). One kind of claim
  fits none of them: what a business term includes ("domestic", "large order", "active customer").
- **Each claim kind mixes a part fixed by the data and a part fixed by convention.** The convention
  part is what checks cannot settle.
- **The "domestic = US + Canada" example is a public term of art**, defined in US DOT reporting rules
  and used in United's SEC filings. A claim can be held by a document, not only by a person.

## 1. Part of speech

| Study | Finding | Caveat |
|---|---|---|
| Fellbaum, Grabowski & Landes 1997 | Taggers agreed with experts most on nouns (p<.01), least on verbs and adjectives | Polysemy explains this "at best only partly" |
| Senseval-2 (Palmer, Dang & Fellbaum 2007) | Inter-tagger agreement 85% for nouns and adjectives pooled, 71% for verbs (82% with grouped senses) | The verbs were chosen as the most polysemous |
| Jurgens 2014 | Instances needing more than one sense: adjectives 15.1%, nouns 10.1%, verbs 8.1% | Author: too few word types to generalise by part of speech |
| Ng, Lim & Foo 1999 | No noun advantage in kappa (0.300 nouns, 0.347 verbs) | Nouns and verbs only |
| Passonneau et al. 2012 (MASC) | Large variation across words; worst item the adjective *normal* (alpha -0.02) | Correlation with number of senses differs by part of speech (0.48 for adjectives) |

Why it is the wrong axis for Warrant:

1. The agent gives "work order" and "domestic" their correct general-English sense; the error is that
   a community fixes a different unit or extension. Agreement studies cannot see this, because general
   readers agree on the wrong reading.
2. Clark (1998) notes that community-specific items are "ordinary nouns, verbs, adjectives, adverbs,
   pronouns, prepositions and so on".
3. Codes such as `+` or `X7` have no part of speech.

Where the intuition holds, it holds one level down, for two subclasses of adjective:

- **Relative gradable adjectives** ("large", "recent", "late") need a threshold from context
  (Kennedy 2007). Absolute ones ("full", "closed") take a scale endpoint and do not.
- **Relational adjectives with an implicit argument** ("domestic", "local", "foreign", "national")
  need a reference point and an extension (Partee 1989; Condoravdi & Gawron 1996). Cappelen & Lepore
  (2005, p. 1) list "foreign, local, domestic, national, imported, exported" among these, though they
  doubt such words are context-sensitive.
- Intersective adjectives ("Canadian") behave like a column filter (Kamp & Partee 1995).

## 2. Three properties of an expression

1. **Which part of the meaning is open**: the counting unit, the domain, the extension, a threshold,
   an anchor, a value's meaning, or a formula.
2. **Who fixes it**: conventional meaning; public facts (Perry's "automatic" indexicals, such as the
   date for "still open"); the structure of the data; a community convention (Clark's communal
   lexicon, Putnam's division of linguistic labour, Searle's "X counts as Y in C"); or an
   organisation's decision.
3. **How familiar the form looks.** A familiar word with a specialised sense (Clark's "specialized
   lemma") predicts silent, confident errors. An opaque form (`X7`) predicts errors the agent notices.

## 3. Claim kinds and their counterparts

| Claim kind | Counterpart | Part fixed by the data | Part fixed by convention |
|---|---|---|---|
| What a table covers | Quantifier domain restriction (Stanley & Szabo 2000; von Fintel 1994) | Symptoms, e.g. a status column with one value | Which population the export was cut from, recorded outside the rows |
| What one row counts as | Individuation, what counts as one (Gupta 1980; Krifka 1990; Rothstein 2010) | Candidate units: parent IDs, many rows per entity | Which unit the word names ("work order" means the parent) |
| What a code means | Communal lexicon (Clark 1998) | Co-occurring fields that hint at a meaning | The assignment of meaning to the code |
| Formulas between columns | Derived-metric definitions (Sheth & Larson 1990; Madnick & Zhu 2006) | Whether an identity holds across rows | Which formula a business term names |
| What a business term includes (does not fit the four above) | Relational and gradable expressions (Partee 1989; Kennedy 2007) | Only if the classification itself is stored, e.g. a region flag | The extension or threshold |

Gupta's standard example is about an airline: "National Airlines served at least two million
passengers" does not imply two million persons, because passengers and persons are counted
differently. Madnick & Zhu report one company's price/earnings ratio on one day as 11.6, 5.57, 19.19
and 7.46 across four sources, because the sources define earnings differently.

## 4. The "domestic" example

- United's 10-Q for Q1 2026, Note 2, has a revenue row "Domestic (U.S. and Canada)". 10-Qs from Q1
  2020 to Q3 2024 introduce the table as "by principal geographic region (as defined by the U.S.
  Department of Transportation)".
- 14 CFR Part 241, Section 21(g): the domestic entity covers the 50 states, DC, Puerto Rico and the
  US Virgin Islands "and shall also include Canadian transborder operations."
- Unverified: a BTS directive (No. 287) may classify Canadian transborder stages as international
  for ICAO reporting. If so, one department gives the word two extensions for two purposes.

Consequences: the word is a term of art, written in a public record, so it can be retrieved as well
as asked about. An agent that reads "domestic" as US-only gets the anchor right and the extension
wrong.

## 5. How to ask: uncertainty and equivocality

Daft & Lengel (1986): uncertainty is not knowing the value of a known variable; equivocality is not
knowing what the variable is. A yes/no question resolves uncertainty ("does this export include open
work orders?"); equivocality needs someone to supply a definition ("what does a work order mean
here?"). Coverage claims look like uncertainty; row-unit claims look like equivocality. Relevant to
#2 (simulated expert) and #3 (answer-time policy).

## 6. A parallel from law: ordinary meaning and terms of art

Courts read a word in its ordinary meaning unless a special trade meaning is proved (*Nix v. Hedden*,
1893, on whether a tomato is a vegetable for a tariff; *Frigaliment*, 1960, on who bears the burden
of proving a trade meaning). An explicit definition in a statute controls even against ordinary
meaning (*Stenberg v. Carhart*, 2000). Under UCC §1-303(c) a trade usage must be proved as a fact; if
it is written in a trade code, interpreting that record is a question of law. An LLM agent defaults
the same way the courts do, without anyone to prove the trade meaning.

## 7. Related work to position against

- Huang, Damalapati & Wu 2023 (NeurIPS TRL workshop), "Data Ambiguity Strikes Back": documenting
  coverage and granularity raised GPT text-to-SQL accuracy (from 80.0% to 86.7% on top of earlier
  documentation levels; small sample). Coverage and row granularity have therefore been studied as
  documentation, though not injected or allocated.
- Jin et al. 2026 (CIDR), "Text-to-SQL Benchmarks Are Broken": the most frequent BIRD annotation
  error is misunderstanding the data, e.g. omitting `rtype='S'` where one table mixes schools and
  districts. That is a naturally occurring row-unit case inside BIRD.
- BIRD-Interact (ICLR 2026): knowledge ambiguities have the lowest success and schema linking the
  highest.

## 8. Testable hypotheses

1. **Familiar words cause silent errors.** Within one claim kind, the same fact probed through a
   familiar word with a local meaning (status `OPEN` meaning something specific) gives more confident
   wrong answers and fewer clarification requests than through an opaque code (`X7`).
2. **The part-of-speech effect disappears once semantic type is coded.** Descriptive only, given
   few terms per cell.
3. **Anchor right, extension wrong.** For "domestic includes Canada", errors are "US only", not the
   wrong country; giving the anchor (the company's country) does not help, giving the extension does.
4. **Detectable but not settleable.** For coverage and row-unit defects the battery flags an anomaly
   but cannot pick the reading; for code-meaning and term-extension defects it flags nothing.
5. **A simulated expert is valid only if restricted** to the reference claims (see #2).

## References

- Cappelen, H., & Lepore, E. (2005). *Insensitive Semantics*. Blackwell.
- Clark, H. H. (1998). Communal lexicons. In *Context in Language Learning and Language Understanding*, 63-87. Cambridge University Press. https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_Communal%20lexicons_%201998.pdf
- Condoravdi, C., & Gawron, J. M. (1996). The context-dependency of implicit arguments. In *Quantifiers, Deduction, and Context*, 1-32. CSLI. https://web.stanford.edu/~cleoc/cdia.pdf
- Daft, R. L., & Lengel, R. H. (1986). Organizational information requirements, media richness and structural design. *Management Science* 32(5), 554-571. https://doi.org/10.1287/mnsc.32.5.554
- Fellbaum, C., Grabowski, J., & Landes, S. (1997). Analysis of a hand-tagging task. ANLP-97 Workshop. https://aclanthology.org/W97-0206/
- Gupta, A. (1980). *The Logic of Common Nouns*. Yale University Press.
- Huang, Z., Damalapati, P. K., & Wu, E. (2023). Data ambiguity strikes back: How documentation improves GPT's text-to-SQL. NeurIPS 2023 TRL Workshop. https://arxiv.org/abs/2310.18742
- Huo, N., et al. (2026). BIRD-INTERACT. ICLR 2026. https://arxiv.org/abs/2510.05318
- Jin, T., Choi, Y., Zhu, Y., & Kang, D. (2026). Text-to-SQL benchmarks are broken: An in-depth analysis of annotation errors. CIDR 2026. https://www.vldb.org/cidrdb/papers/2026/p5-jin.pdf
- Jurgens, D. (2014). An analysis of ambiguity in word sense annotations. LREC 2014. http://www.lrec-conf.org/proceedings/lrec2014/pdf/904_Paper.pdf
- Kamp, H., & Partee, B. (1995). Prototype theory and compositionality. *Cognition* 57, 129-191.
- Kennedy, C. (2007). Vagueness and grammar. *Linguistics and Philosophy* 30(1), 1-45. https://doi.org/10.1007/s10988-006-9008-0
- Krifka, M. (1990). Four thousand ships passed through the lock. *Linguistics and Philosophy* 13(5), 487-520. https://doi.org/10.1007/BF00627291
- Madnick, S., & Zhu, H. (2006). Improving data quality through effective use of data semantics. *Data & Knowledge Engineering* 59(2), 460-475. https://doi.org/10.1016/j.datak.2005.10.001
- Ng, H. T., Lim, C. Y., & Foo, S. K. (1999). A case study on inter-annotator agreement for word sense disambiguation. SIGLEX99. https://aclanthology.org/W99-0502/
- Palmer, M., Dang, H. T., & Fellbaum, C. (2007). Making fine-grained and coarse-grained sense distinctions. *Natural Language Engineering* 13(2), 137-163. https://doi.org/10.1017/S135132490500402X
- Partee, B. H. (1989). Binding implicit variables in quantified contexts. CLS 25, 342-365.
- Passonneau, R. J., Baker, C., Fellbaum, C., & Ide, N. (2012). The MASC word sense corpus. LREC 2012. https://aclanthology.org/L12-1335/
- Perry, J. (1997). Indexicals and demonstratives. In *A Companion to the Philosophy of Language*. Blackwell. http://john.jperry.net/cv/1997a.pdf
- Putnam, H. (1975). The meaning of "meaning". *Minnesota Studies in the Philosophy of Science* 7, 131-193. https://hdl.handle.net/11299/185225
- Rothstein, S. (2010). Counting and the mass/count distinction. *Journal of Semantics* 27(3), 343-397. https://doi.org/10.1093/jos/ffq007
- Searle, J. R. (1995). *The Construction of Social Reality*. Free Press.
- Sheth, A. P., & Larson, J. A. (1990). Federated database systems. *ACM Computing Surveys* 22(3), 183-236. https://doi.org/10.1145/96602.96604
- Stanley, J., & Szabo, Z. G. (2000). On quantifier domain restriction. *Mind & Language* 15(2-3), 219-261. https://doi.org/10.1111/1468-0017.00130
- von Fintel, K. (1994). *Restrictions on Quantifier Domains*. PhD dissertation, UMass Amherst.
- *Nix v. Hedden*, 149 U.S. 304 (1893). https://supreme.justia.com/cases/federal/us/149/304/
- *Frigaliment Importing Co. v. B.N.S. International Sales Corp.*, 190 F. Supp. 116 (S.D.N.Y. 1960). https://law.justia.com/cases/federal/district-courts/FSupp/190/116/1622834/
- *Stenberg v. Carhart*, 530 U.S. 914 (2000).
- Uniform Commercial Code §1-303(c). https://www.law.cornell.edu/ucc/1/1-303
- 14 CFR Part 241, Section 21(g). https://www.law.cornell.edu/cfr/text/14/21
- United Airlines Holdings, Form 10-Q, Q1 2026. https://www.sec.gov/Archives/edgar/data/100517/000010051726000091/ual-20260331.htm
- United Airlines Holdings, Form 10-Q, Q3 2024. https://www.sec.gov/Archives/edgar/data/100517/000010051724000136/ual-20240930.htm
