# Challenge Results And Failure Analysis

## Accepted Retrieval Matrix

The 64-case synthetic and anonymized challenge set is evaluated with the same documents, top-k, and runtime configuration across every path. It uses 16 files, including five clearly marked historical archives with overlapping vocabulary, and 400-character chunks with 120-character overlap.

| Path | Recall@1 | Recall@3 | Recall@5 | Precision@3 | nDCG@5 | MRR@10 | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TEXT | 45.7% | 71.7% | 82.6% | 23.9% | 0.650 | 0.616 | 0.0% |
| VECTOR | 54.3% | 89.1% | 95.7% | 29.7% | 0.774 | 0.718 | 0.0% |
| HYBRID | 56.5% | 91.3% | 97.8% | 30.4% | 0.801 | 0.745 | 0.0% |
| HYBRID+Graph | 56.5% | 89.1% | 97.8% | 29.7% | 0.797 | 0.739 | 40.0% |

Source reports: `eval/reports/challenge_matrix.md` and the per-path Markdown and JSON payloads in `eval/reports/`.

## What The Matrix Shows

- HYBRID has the best ranking result in this run: `nDCG@5=0.801` and `MRR@10=0.745`, above VECTOR (`0.774`, `0.718`) and TEXT (`0.650`, `0.616`).
- Graph expansion preserves HYBRID Recall@5 while adding source-traceable graph evidence to 40% of relationship questions. It lowers `nDCG@5` by `0.004` and `MRR@10` by `0.006`, so it should remain conditionally routed rather than enabled blindly.
- The graph is useful when a question needs a relationship path or when BM25 and vector retrieval disagree. It is not a default replacement for direct retrieval.

## Known Failures

The denser corpus intentionally reveals three unfinished quality issues:

1. **No-answer calibration:** none of 18 negative questions are rejected in the current dense-corpus run (`0.0%`). The current lexical threshold accepts policy-adjacent but unsupported questions. The next retrieval-calibration change should improve this rate without reducing positive answer rate or Recall@5.
2. **Graph evidence coverage:** 4 of 10 relationship questions return the expected shared entity path (`40.0%`). The graph routes 9 of 10 relationship queries and returns graph candidates for 9 of 10, so the main gap is entity-path precision rather than router availability.
3. **Answer faithfulness scope:** the HYBRID `/ask` run has `Citation coverage=91.3%`. The extractive fallback reaches `Extractive citation faithfulness=100.0%` over 46 evaluable positive answers because it copies a cited preview. This does not validate an LLM paraphrase; semantic faithfulness needs an LLM judge or human review set.

These figures are not production claims. The corpus is synthetic; the value of this project is that the limitations are measurable, reproducible, and protected by a quality gate. Current reports also include `Recall@1`, `Precision@3/5`, `nDCG@3/5`, and extractive citation faithfulness. The last metric is deliberately limited to the extractive fallback; an LLM answer needs a judge model or human review before claiming semantic faithfulness.

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
