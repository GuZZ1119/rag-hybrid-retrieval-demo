# Challenge Retrieval Comparison

This matrix compares the same labelled dataset with graph expansion disabled and enabled.

| Path | Recall@1 | Recall@3 | Recall@5 | Precision@3 | nDCG@5 | MRR@10 | Negative no-answer | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TEXT | 50.0% | 73.5% | 85.3% | 26.5% | 66.8% | 0.652 | 0.0% | 0.0% |
| VECTOR | 55.9% | 88.2% | 94.1% | 31.4% | 76.7% | 0.728 | 0.0% | 0.0% |
| HYBRID | 61.8% | 91.2% | 97.1% | 32.4% | 79.3% | 0.760 | 0.0% | 0.0% |
| HYBRID+Graph | 61.8% | 91.2% | 97.1% | 32.4% | 79.3% | 0.760 | 0.0% | 36.4% |
