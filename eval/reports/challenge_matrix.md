# Challenge Retrieval Comparison

This matrix compares the same labelled dataset with graph expansion disabled and enabled.

| Path | Recall@1 | Recall@3 | Recall@5 | Precision@3 | nDCG@5 | MRR@10 | Negative no-answer | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TEXT | 45.7% | 71.7% | 82.6% | 23.9% | 65.0% | 0.616 | 0.0% | 0.0% |
| VECTOR | 54.3% | 89.1% | 95.7% | 29.7% | 77.4% | 0.718 | 0.0% | 0.0% |
| HYBRID | 56.5% | 91.3% | 97.8% | 30.4% | 80.1% | 0.745 | 0.0% | 0.0% |
| HYBRID+Graph | 56.5% | 89.1% | 97.8% | 29.7% | 79.7% | 0.739 | 0.0% | 40.0% |
