# Challenge Retrieval Comparison

This matrix compares the same labelled dataset with graph expansion disabled and enabled.

| Path | Recall@3 | Recall@5 | MRR@10 | Negative no-answer | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: |
| TEXT | 100.0% | 100.0% | 0.920 | 0.0% | 0.0% |
| VECTOR | 97.8% | 100.0% | 0.864 | 0.0% | 0.0% |
| HYBRID | 100.0% | 100.0% | 0.931 | 16.7% | 0.0% |
| HYBRID+Graph | 100.0% | 100.0% | 0.931 | 16.7% | 40.0% |
