# Challenge Results And Failure Analysis

## Accepted Retrieval Matrix

The 64-case synthetic and anonymized challenge set is evaluated with the same documents, top-k, and runtime configuration across every path.

| Path | Recall@3 | Recall@5 | MRR@10 | Negative no-answer | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: |
| TEXT | 100.0% | 100.0% | 0.920 | 0.0% | 0.0% |
| VECTOR | 97.8% | 100.0% | 0.864 | 0.0% | 0.0% |
| HYBRID | 100.0% | 100.0% | 0.931 | 16.7% | 0.0% |
| HYBRID+Graph | 100.0% | 100.0% | 0.931 | 16.7% | 40.0% |

Source reports: `eval/reports/challenge_matrix.md` and the per-path Markdown and JSON payloads in `eval/reports/`.

## What The Matrix Shows

- HYBRID has the best ranking result in this set: `MRR@10=0.931`, above TEXT (`0.920`) and VECTOR (`0.864`).
- Graph expansion preserves HYBRID Recall@5 and MRR while adding source-traceable graph evidence to 40% of relationship questions.
- The graph is useful when a question needs a relationship path or when BM25 and vector retrieval disagree. It is not a default replacement for direct retrieval.

## Known Failures

The expanded set intentionally reveals two unfinished quality issues:

1. **No-answer calibration:** only 3 of 18 negative questions are rejected (`16.7%`). The current lexical threshold accepts policy-adjacent but unsupported questions. The next retrieval-calibration change should improve this rate without reducing positive answer rate or Recall@5.
2. **Graph evidence coverage:** 4 of 10 relationship questions return the expected shared entity path (`40.0%`). The graph routes 9 of 10 relationship queries and returns graph candidates for 9 of 10, so the main gap is entity-path precision rather than router availability.

These figures are not production claims. The corpus is small and synthetic; the value of this project is that the limitations are measurable, reproducible, and protected by a quality gate.

## Reproduce Or Compare

```bash
cd demo
EVAL_REVISION="$(git rev-parse HEAD)" docker compose exec -e EVAL_REVISION \
  kb-api python /app/eval/run_experiment_matrix.py --bootstrap

docker compose exec kb-api python /app/eval/quality_gate.py \
  --baseline /app/eval/reports/challenge_hybrid_graph.json \
  --candidate /app/eval/reports/candidate_hybrid_graph.json
```

The JSON metric payload records the source revision, dataset checksum, mode, graph setting, top-k, and runtime configuration. The gate rejects non-comparable runs and material regressions.
