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

## Run

From the `demo` directory:

```bash
docker compose exec kb-api python /app/eval/run_retrieval_eval.py \
  --bootstrap \
  --mode HYBRID \
  --endpoint ask \
  --output /app/eval/reports/quality_baseline.md
```
