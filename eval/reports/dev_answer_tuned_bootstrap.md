# Paired Bootstrap Comparison

- Baseline: `dev_answer_baseline.json`
- Candidate: `dev_answer_tuned.json`
- Method: paired non-parametric bootstrap over shared eligible cases; 95% percentile confidence interval for candidate minus baseline. Eligibility counts are reported because answer metrics can be unavailable after a no-answer decision.

| Metric | Paired / baseline / candidate eligible | Baseline | Candidate | Delta | 95% CI | P(delta > 0) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| answer_correctness | 16 / 16 / 16 | 0.750 | 0.875 | +0.125 | [-0.125, +0.375] | 0.777 |
| citation_correctness | 16 / 16 / 16 | 0.292 | 0.500 | +0.208 | [+0.167, +0.271] | 1.000 |
| citation_completeness | 16 / 16 / 16 | 0.875 | 0.969 | +0.094 | [+0.000, +0.250] | 0.879 |
| negative_no_answer_rate | 5 / 5 / 5 | 0.000 | 0.200 | +0.200 | [+0.000, +0.600] | 0.688 |
