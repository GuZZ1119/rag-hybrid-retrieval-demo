# Challenge Golden Set

`golden_qa.jsonl` is a fixed, synthetic and anonymized evaluation set for the enterprise-file RAG demo. It is deliberately small enough to inspect by hand and difficult enough to reveal retrieval regressions.

## Dataset Design

The current set has 64 labelled cases. The evaluation corpus has 16 files: 11 controlled policy documents and 5 explicitly marked historical archives with overlapping vocabulary. With the Docker default chunk size of 400 and overlap of 120, this produces a multi-chunk retrieval pool instead of treating each source file as one candidate.

- 22 keyword queries
- 14 paraphrased queries
- 10 cross-document relationship queries
- 18 negative queries that should return `NO_ANSWER`

Each item has a retrieval `category`, a `difficulty` (`standard` or `challenge`), and a `scenario` label. Scenarios cover baseline lookup, semantic paraphrase, cross-document evidence, distractors, multi-condition rules, version conflicts, and negative questions.

Positive cases identify one expected evidence chunk through a file and source terms. Relationship cases additionally identify the expected shared graph entity. The labels make retrieval outcomes deterministic and keep this project focused on evidence retrieval rather than subjective answer grading. Historical archives are deliberately not expected evidence: a version-conflict answer must retrieve the current controlled document.

## Metrics

- `Recall@1/3/5`: whether a labelled evidence chunk appears within the candidate depth. `Recall@1` is the more discriminating indicator once the corpus contains close distractors.
- `Precision@3/5 (one-label)`: relevant candidates divided by `k`, averaged over positive queries. Each current query has one primary labelled chunk, so the theoretical ceiling is `33.3%` at 3 and `20.0%` at 5; use it as a ranking-purity trend, not a standalone success percentage.
- `nDCG@3/5`: rank-sensitive graded relevance. Primary evidence has grade 3 and future labels may add grade-1 supporting evidence.
- `MRR@10`: reciprocal rank of the first labelled evidence chunk.
- `Extractive citation faithfulness`: only for the runnable extractive fallback. It checks that the returned answer includes a cited source preview. It intentionally skips `answerMode=LLM`; semantic LLM faithfulness still needs an LLM judge or human annotation.

## Current Challenge Baseline

The Docker HYBRID `/ask` baseline is recorded in `reports/quality_baseline.md`.

After introducing the archival distractor corpus and smaller chunks, the current `HYBRID+Graph` search run reaches `Recall@1=56.5%`, `Recall@3=89.1%`, `Recall@5=97.8%`, `Precision@3=29.7%`, `nDCG@5=0.797`, and `MRR@10=0.739`. Graph evidence coverage on relationship cases is `40.0%`.

The `/ask` baseline records `Citation coverage=91.3%` and `Extractive citation faithfulness=100.0%` across 46 evaluable positive answers. Its negative no-answer rate is currently `0.0%`; the denser corpus has exposed no-answer calibration as the next retrieval-quality target. These diagnostic metrics should not be improved by removing hard negatives or weakening the relationship labels.

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

The default gate allows small documented movement (`Recall@5`, `Precision@3`, `nDCG@5`, no-answer rate, citation coverage, and extractive citation faithfulness: 5 points; `MRR@10`: 0.03) but rejects larger regressions or a changed dataset checksum. Metrics not applicable to an endpoint are skipped, so run the gate on like-for-like `/search` or `/ask` payloads.

The accepted 64-case retrieval matrix is stored in `reports/challenge_matrix.md`. Its current result is: TEXT `MRR@10=0.616`, VECTOR `0.718`, HYBRID `0.745`, and HYBRID+Graph `0.739`. Graph expansion keeps Recall@5 at `97.8%`, raises relationship evidence coverage from `0.0%` to `40.0%`, and has a small ranking cost that remains visible in the report.

## Run

From the `demo` directory:

```bash
docker compose exec kb-api python /app/eval/run_retrieval_eval.py \
  --bootstrap \
  --mode HYBRID \
  --endpoint ask \
  --output /app/eval/reports/quality_baseline.md
```
