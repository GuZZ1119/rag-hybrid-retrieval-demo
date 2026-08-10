# Challenge Golden Set

`golden_qa.jsonl` is a fixed, synthetic and anonymized evaluation set for the enterprise-file RAG demo. It is deliberately small enough to inspect by hand and difficult enough to reveal retrieval regressions.

## Dataset Design

The current set has 64 labelled cases:

- 22 keyword queries
- 14 paraphrased queries
- 10 cross-document relationship queries
- 18 negative queries that should return `NO_ANSWER`

Each item has a retrieval `category`, a `difficulty` (`standard` or `challenge`), and a `scenario` label. Scenarios cover baseline lookup, semantic paraphrase, cross-document evidence, distractors, multi-condition rules, version conflicts, and negative questions.

Positive cases identify one expected file and source terms. Relationship cases additionally identify the expected shared graph entity. The labels make retrieval outcomes deterministic and keep this project focused on evidence retrieval rather than subjective answer grading.

## Current Challenge Baseline

The Docker HYBRID `/ask` baseline is recorded in `reports/quality_baseline.md`.

On the first 64-case run, the demo reached `Recall@3=100%`, `Recall@5=100%`, and `MRR@10=0.931`. The negative no-answer rate was `16.7%`, while graph evidence coverage on relationship cases was `40.0%`.

These lower diagnostic metrics are intentional follow-up targets. They should not be hidden by removing hard negatives or weakening the relationship labels.

## Compare And Gate

Run the same data through `TEXT`, `VECTOR`, `HYBRID`, and `HYBRID+Graph`:

```bash
docker compose exec kb-api python /app/eval/run_experiment_matrix.py --bootstrap
```

The matrix writes per-path Markdown and JSON payloads plus `reports/challenge_matrix.md`. JSON payloads contain the dataset checksum, retrieval configuration, and metrics, so a candidate run can be checked against an accepted baseline:

```bash
docker compose exec kb-api python /app/eval/quality_gate.py \
  --baseline /app/eval/reports/challenge_hybrid_graph.json \
  --candidate /app/eval/reports/candidate_hybrid_graph.json
```

The default gate allows small documented movement (`Recall@5`: 5 points, `MRR@10`: 0.03, no-answer rate: 5 points, citation coverage: 5 points) but rejects larger regressions or a changed dataset checksum.

The accepted 64-case retrieval matrix is stored in `reports/challenge_matrix.md`. Its current result is: TEXT `MRR@10=0.920`, VECTOR `0.864`, HYBRID `0.931`, and HYBRID+Graph `0.931`. Graph expansion raises relationship evidence coverage from `0.0%` to `40.0%` without reducing Recall@5 or MRR.

## Run

From the `demo` directory:

```bash
docker compose exec kb-api python /app/eval/run_retrieval_eval.py \
  --bootstrap \
  --mode HYBRID \
  --endpoint ask \
  --output /app/eval/reports/quality_baseline.md
```
