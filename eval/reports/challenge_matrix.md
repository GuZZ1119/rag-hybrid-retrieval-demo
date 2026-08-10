# Challenge Retrieval Comparison

This matrix compares the same labelled dataset with graph expansion disabled and enabled.

| Path | Recall@1 | Recall@3 | Recall@5 | Precision@3 | nDCG@5 | MRR@10 | Negative no-answer | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TEXT | 45.2% | 71.0% | 83.9% | 23.7% | 65.6% | 0.618 | 0.0% | 0.0% |
| VECTOR | 51.6% | 87.1% | 93.5% | 29.0% | 75.5% | 0.702 | 0.0% | 0.0% |
| HYBRID | 58.1% | 90.3% | 96.8% | 30.1% | 79.1% | 0.737 | 0.0% | 0.0% |
| HYBRID+Graph | 58.1% | 90.3% | 96.8% | 30.1% | 79.1% | 0.737 | 0.0% | 50.0% |
