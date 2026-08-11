# Challenge Results And Failure Analysis

## Accepted Retrieval Matrix

The accepted baseline uses the held-out 47-case test split of the synthetic and anonymized challenge set. It uses a frozen 16-file corpus, SHA-checked fixture manifest, immutable chunk-level qrels, and 400-character chunks with 120-character overlap. The interactive demo and evaluation service use separate OpenSearch indexes and data volumes. Three added multi-evidence test cases require evidence across current and archived versioned policy documents or across two controlled documents.

| Path | Recall@1 | Recall@3 | Recall@5 | Precision@3 | nDCG@5 | MRR@10 | Graph evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TEXT | 50.0% | 73.5% | 85.3% | 26.5% | 0.668 | 0.652 | 0.0% |
| VECTOR | 55.9% | 88.2% | 94.1% | 31.4% | 0.767 | 0.728 | 0.0% |
| HYBRID | 61.8% | 91.2% | 97.1% | 32.4% | 0.793 | 0.760 | 0.0% |
| HYBRID+Graph | 61.8% | 91.2% | 97.1% | 32.4% | 0.793 | 0.760 | 36.4% |

Source reports: `eval/reports/challenge_matrix.md` and the per-path Markdown and JSON payloads in `eval/reports/`.

## What The Matrix Shows

- HYBRID has the best test ranking result: `nDCG@5=0.793` and `MRR@10=0.760`, above VECTOR (`0.767`, `0.728`) and TEXT (`0.668`, `0.652`).
- Graph expansion preserves HYBRID ranking in this held-out run while adding source-traceable graph evidence to 36.4% of relationship questions. The paired bootstrap comparison has zero observed ranking delta and `[0.000, 0.000]` 95% intervals for Recall@5, nDCG@5, and MRR@10, so this run provides no evidence of a ranking gain; graph value is limited to inspectable relation evidence.
- The graph is useful when a question needs a relationship path or when BM25 and vector retrieval disagree. It is not a default replacement for direct retrieval.

## Known Failures

The denser corpus intentionally reveals three unfinished quality issues:

1. **No-answer calibration:** none of 13 test negatives are rejected (`0.0%`). The current lexical threshold accepts policy-adjacent but unsupported questions. Tune this only on the dev split, then report the untouched test result.
2. **Graph evidence coverage:** 4 of 11 held-out relationship questions return the expected shared entity path (`36.4%`). The router and graph candidate coverage are both `81.8%`, so the main gap remains entity-path precision rather than router availability.
3. **Answer completeness:** the held-out HYBRID `/ask` run has `Answer correctness=54.4%`, `Citation correctness=32.4%`, and `Citation completeness` will expose any uncited required source in a multi-evidence claim. The extractive fallback's `Extractive claim faithfulness=100.0%` only means each copied clause appears in a cited preview; it does not validate an LLM paraphrase.

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
