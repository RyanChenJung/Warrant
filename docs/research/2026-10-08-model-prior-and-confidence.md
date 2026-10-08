# The model's prior knowledge and confidence routing

2026-10-08. Two literature sweeps, an inventory of the team's BIRD obfuscation pipeline, and a
reviewer-style critique, run while deciding how to treat claims an LLM writes from its own prior
knowledge rather than from the data. Citations were checked against their landing pages; the full
list with links is in the author's reading list.

## The question

Besides the data and a person, a model's prior knowledge is a third source of support. An LLM guesses
"'+' means carcinogenic" from a toxicology database name: the data did not settle it, the prior did.
The first idea was to route such claims by confidence: very confident, write it marked as not
confirmed by a person (a provisional claim); otherwise ask a person.

## Findings

1. **Measuring "how often a confident prior is right" would replicate known results.** Accuracy
   tracks how popular a fact is (Mallen et al. 2023; Kandpal et al. 2023); wrong answers are more
   popular and get higher confidence (Ni et al. 2025); self-reported confidence is too high (Xiong et
   al. 2024); and even a calibrated model must hallucinate on arbitrary facts (Kalai & Vempala 2024),
   which is what a company's own codes are. Such a measurement also produces no allocation, and its
   overall rate is set by how many defects we inject; report conditional rates instead.
2. **The two rules disagree only where the data cannot settle a claim but the model is confident.**
   The decisive case is a prior that is present but wrong: a familiar-looking code whose meaning is
   local.
3. **The obfuscation pipeline does not remove the prior.** It renames tables and columns (translated
   per database into one of five languages; English databases keep their names) but leaves values,
   database names, question wording and the meaning of evidence unchanged. Renaming mostly tests
   schema linking: with positional identifiers on BIRD mini-dev, most errors become wrong-column
   picks (Su et al. 2026).
4. **Value-only recoding is a clean manipulation.** Three versions of the same data: original codes
   (the prior helps), arbitrary codes (no prior), swapped codes such as '+' and '-' exchanged (the
   prior is present and wrong). Checks that look only inside the data give the same verdict under any
   relabelling, so the decidability rule decides identically in all three; only confidence-based
   rules can change, and only because of the prior.
5. **Closest precedents.** Flipped and unrelated labels remove or invert the prior (Wei et al. 2023);
   entity substitution (Longpre et al. 2021); prior strength against context (ClashEval, Wu, Wu & Zou
   2024); counterfactual databases with the same schema (ContraTable, Wang & Liu 2026); routing
   column-name expansions to human review by an LLM-judge score (TACO, Cai et al. 2026); a verifier
   beating LLM uncertainty at picking labels for human review (Wang et al. 2024, Lapras). Counter-
   evidence: simple uncertainty estimates are competitive for deciding when to trust parametric
   memory (Moskvoretskii et al. 2025). The only measurement found of renaming against confidence is
   in code, with a model-dependent direction (Le, Nguyen & Nguyen 2026).
6. **Confidence estimators.** The Claude API exposes no token probabilities, so confidence comes from
   agreement over repeated samples plus self-report. Decision-only models such as Jev (TypeSafe,
   early access September 2026) need candidate options supplied, which inflates accuracy, and show
   weak calibration out of distribution (Deußer, Sparrenberg & Sifa 2026; the jev-ood-calibration
   repository). Accepting confident verdicts and escalating the rest is itself published
   (JEV-as-a-Judge, Li et al. 2026), so the confidence layer is not new.

## How it was folded into the design

- No separate model-prior experiment. The confidence rule (the baseline) and the hybrid rule that
  writes provisional claims are columns of the allocation table.
- Swapped-code defects are value-meaning injected defects; leaving the documentation unchanged makes
  them stale documentation as well.
- A memorisation check runs in week one, because original BIRD is public: renaming identifiers cost
  one model about 4.8 points without hints (5 to 10 points in some languages), which shows it
  remembers names, not that it has memorised answers. Remembered meanings act like invisible stale
  documentation for value-meaning and term-boundary defects.
- Familiar words against opaque codes is labelled on every probe question; the paired experiment is
  issue #4.
- The confidence threshold is tuned on databases outside the showcase set and frozen (ADR 0002).

## Quantities to report

- The share of swapped-code claims, not settled by the battery, on which the model's confidence is
  still above the frozen threshold: the rate at which confidence routing writes a wrong claim.
- Wrong writes against the share of misleading codes in a deployment: flat at zero for the
  decidability rule (at the cost of a fixed number of person asks), rising with that share for
  confidence routing.

## References

- Deußer, T., Sparrenberg, L., & Sifa, R. (2026). Evaluating and benchmarking the System One model Jev. arXiv 2609.37647. https://arxiv.org/abs/2609.37647
- Kalai, A. T., & Vempala, S. S. (2024). Calibrated language models must hallucinate. STOC 2024. https://arxiv.org/abs/2311.14648
- Kandpal, N., et al. (2023). Large language models struggle to learn long-tail knowledge. ICML 2023. https://proceedings.mlr.press/v202/kandpal23a.html
- Le, J., Nguyen, A. H. N., & Nguyen, T. N. (2026). Do machines struggle where humans do? LLM and human comprehension of obfuscated code. arXiv 2606.31725. https://arxiv.org/abs/2606.31725
- Li, Y., Miao, Y., Krishnan, R., & Padman, R. (2026). JEV-as-a-Judge: Accept when confident, escalate when unsure. arXiv 2609.26550. https://arxiv.org/abs/2609.26550
- Longpre, S., et al. (2021). Entity-based knowledge conflicts in question answering. EMNLP 2021. https://aclanthology.org/2021.emnlp-main.565/
- Mallen, A., et al. (2023). When not to trust language models. ACL 2023. https://aclanthology.org/2023.acl-long.546/
- Moskvoretskii, V., et al. (2025). Adaptive retrieval without self-knowledge? Bringing uncertainty back home. ACL 2025. https://aclanthology.org/2025.acl-long.319/
- Ni, S., Bi, K., Guo, J., & Cheng, X. (2025). Popular but wrong: Understanding and mitigating LLM overconfidence through knowledge popularity. arXiv 2505.17537. https://arxiv.org/abs/2505.17537
- Su, D. Y., et al. (2026). Disentangling structure and semantics: How schema representation affects LLM-based SQL generation. arXiv 2608.20356. https://arxiv.org/abs/2608.20356
- Cai, T., et al. (2026). TACO: Task-aware column description generation using LLMs. arXiv 2606.21685. https://arxiv.org/abs/2606.21685
- Wang, X., & Liu, C. (2026). The table says otherwise: Testing LLMs with counterfactual relational data. arXiv 2606.23667. https://arxiv.org/abs/2606.23667
- Wang, X., et al. (2024). Human-LLM collaborative annotation through effective verification of LLM labels. CHI 2024. https://doi.org/10.1145/3613904.3641960
- Wei, J., et al. (2023). Larger language models do in-context learning differently. arXiv 2303.03846. https://arxiv.org/abs/2303.03846
- Wu, K., Wu, E., & Zou, J. (2024). ClashEval: Quantifying the tug-of-war between an LLM's internal prior and external evidence. NeurIPS 2024 Datasets and Benchmarks. https://arxiv.org/abs/2404.10198
- Xiong, M., et al. (2024). Can LLMs express their uncertainty? ICLR 2024. https://openreview.net/forum?id=gjeQKFxFpZ
