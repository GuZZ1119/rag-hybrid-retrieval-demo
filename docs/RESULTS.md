# Challenge Results And Failure Analysis

## Accepted Retrieval Matrix

The accepted baseline uses the held-out 44-case test split of the synthetic and anonymized challenge set. It uses a frozen 16-file corpus, SHA-checked fixture manifest, immutable chunk-level qrels, and 400-character chunks with 120-character overlap. The interactive demo and evaluation service use separate OpenSearch indexes and data volumes.

| Path | Recall@1 | Recall@3 | Recall@5 | Precision@3 | nDCG@5 | MRR@10 | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TEXT | 45.2% | 71.0% | 83.9% | 23.7% | 0.656 | 0.618 | 0.0% |
| VECTOR | 51.6% | 87.1% | 93.5% | 29.0% | 0.755 | 0.702 | 0.0% |
| HYBRID | 58.1% | 90.3% | 96.8% | 30.1% | 0.791 | 0.737 | 0.0% |
| HYBRID+Graph | 58.1% | 90.3% | 96.8% | 30.1% | 0.791 | 0.737 | 50.0% |

Source reports: `eval/reports/challenge_matrix.md` and the per-path Markdown and JSON payloads in `eval/reports/`.

## What The Matrix Shows

- HYBRID has the best test ranking result: `nDCG@5=0.791` and `MRR@10=0.737`, above VECTOR (`0.755`, `0.702`) and TEXT (`0.656`, `0.618`).
- Graph expansion preserves HYBRID ranking in this held-out run while adding source-traceable graph evidence to 50% of relationship questions. It remains conditionally routed rather than enabled blindly.
- The graph is useful when a question needs a relationship path or when BM25 and vector retrieval disagree. It is not a default replacement for direct retrieval.

## Known Failures

The denser corpus intentionally reveals three unfinished quality issues:

1. **No-answer calibration:** none of 13 test negatives are rejected (`0.0%`). The current lexical threshold accepts policy-adjacent but unsupported questions. Tune this only on the dev split, then report the untouched test result.
2. **Graph evidence coverage:** 4 of 8 held-out relationship questions return the expected shared entity path (`50.0%`). The router and graph candidate coverage are both `100.0%`, so the main gap remains entity-path precision rather than router availability.
3. **Answer faithfulness scope:** the held-out HYBRID `/ask` run has chunk-level `Citation coverage=90.3%`. The extractive fallback reaches `Extractive citation faithfulness=100.0%` over 31 evaluable positive answers because it copies a cited preview. This does not validate an LLM paraphrase; semantic faithfulness needs an LLM judge or human review set.

These figures are not production claims. The corpus is synthetic; the value of this project is that the limitations are measurable, reproducible, and protected by a quality gate. Current reports also include `Recall@1`, `Precision@3/5`, `nDCG@3/5`, and extractive citation faithfulness. The last metric is deliberately limited to the extractive fallback; an LLM answer needs a judge model or human review before claiming semantic faithfulness.

## Reproduce Or Compare

```bash
cd demo
docker compose up -d --build
EVAL_REVISION="$(git rev-parse HEAD)" docker compose exec -e EVAL_REVISION \
  kb-eval-api python /app/eval/run_experiment_matrix.py --bootstrap --split test

docker compose exec kb-eval-api python /app/eval/quality_gate.py \
  --baseline /app/eval/reports/challenge_hybrid_graph.json \
  --candidate /app/eval/reports/candidate_hybrid_graph.json
```

The JSON metric payload records the source revision, dataset, qrels, split, corpus-manifest checksums, mode, graph setting, top-k, and runtime configuration. The gate rejects non-comparable runs and material regressions.
