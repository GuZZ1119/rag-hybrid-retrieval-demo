# Paired Bootstrap Comparison

- Baseline: `challenge_hybrid.json`
- Candidate: `challenge_hybrid_graph.json`
- Method: paired non-parametric bootstrap over the same eligible cases; 95% percentile confidence interval for candidate minus baseline.

| Metric | Paired cases | Baseline | Candidate | Delta | 95% CI | P(delta > 0) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| recall_at_5 | 34 | 0.971 | 0.971 | +0.000 | [+0.000, +0.000] | 0.000 |
| ndcg_at_5 | 34 | 0.793 | 0.793 | +0.000 | [+0.000, +0.000] | 0.000 |
| mrr_at_10 | 34 | 0.760 | 0.760 | +0.000 | [+0.000, +0.000] | 0.000 |
