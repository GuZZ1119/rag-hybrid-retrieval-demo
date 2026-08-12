# Paired Bootstrap Comparison

- Baseline: `quality_baseline.json`
- Candidate: `answer_evidence_test.json`
- Method: paired non-parametric bootstrap over shared eligible cases; 95% percentile confidence interval for candidate minus baseline. Eligibility counts are reported because answer metrics can be unavailable after a no-answer decision.

| Metric | Paired / baseline / candidate eligible | Baseline | Candidate | Delta | 95% CI | P(delta > 0) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| recall_at_5 | 34 / 34 / 34 | 0.971 | 0.971 | +0.000 | [+0.000, +0.000] | 0.000 |
| ndcg_at_5 | 34 / 34 / 34 | 0.793 | 0.793 | +0.000 | [+0.000, +0.000] | 0.000 |
| mrr_at_10 | 34 / 34 / 34 | 0.760 | 0.760 | +0.000 | [+0.000, +0.000] | 0.000 |
| answer_correctness | 34 / 34 / 34 | 0.544 | 0.853 | +0.309 | [+0.147, +0.485] | 1.000 |
| citation_correctness | 34 / 34 / 34 | 0.324 | 0.515 | +0.191 | [+0.162, +0.225] | 1.000 |
| citation_completeness | 34 / 34 / 34 | 0.897 | 0.956 | +0.059 | [+0.000, +0.147] | 0.875 |
| negative_no_answer_rate | 13 / 13 / 13 | 0.000 | 0.538 | +0.538 | [+0.231, +0.769] | 1.000 |
