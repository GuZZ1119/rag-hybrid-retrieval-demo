# Challenge Golden Set

`golden_qa.jsonl` is a fixed, synthetic and anonymized evaluation set for the enterprise-file RAG demo. It is deliberately small enough to inspect by hand and difficult enough to reveal retrieval regressions.

## Frozen Evaluation Protocol

The benchmark is deliberately separated from the interactive demo environment.

- `split_manifest.json` freezes 20 development cases and 44 held-out test cases. Tune chunking, retrieval weights, graph routing, and no-answer thresholds only on `dev`; release reports and quality gates default to `test`.
- `corpus_manifest.json` freezes every fixture filename, SHA-256, deterministic file ID, and the 400/120 chunking contract.
- `qrels.jsonl` maps every positive query to immutable `fileId:chunkIndex` relevance labels. Changing the corpus or chunking requires a new manifest and new qrels, rather than silently changing the definition of a hit.
- Docker service `kb-eval-api` uses its own `kb-eval-*` OpenSearch indexes and `kb-eval-data` volume. The evaluator rejects any uploaded file outside the frozen manifest.

## Dataset Design

The full set has 68 labelled cases: 21 development and 47 held-out test. The evaluation corpus has 16 files: 11 controlled policy documents and 5 explicitly marked historical archives with overlapping vocabulary. The test split includes version-conflict and multi-hop cases whose qrels require evidence from more than one frozen chunk. With the frozen 400-character chunk size and 120-character overlap, this produces a multi-chunk retrieval pool instead of treating each source file as one candidate.

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
- `Extractive claim faithfulness`: splits the extractive answer into sentence-level clauses and verifies each clause against cited previews. It is deterministic for the fallback and intentionally does not score LLM paraphrases.
- `Answer correctness (reference claims)`: percentage of annotated atomic claims whose required terms appear in the answer. It makes incomplete multi-hop answers visible without claiming semantic equivalence.
- `Citation correctness`: percentage of returned citations that point to a chunk supporting at least one annotated atomic claim.
- `Citation completeness`: percentage of atomic claims for which every required supporting chunk is cited. Multi-evidence claims therefore fail this metric when one required source is missing.

## Current Challenge Baseline

The Docker HYBRID `/ask` baseline is recorded in `reports/quality_baseline.md`.

The earlier 64-case report predates frozen qrels and is retained only as historical context. Regenerate the accepted baseline on the isolated 44-case test split before comparing a new implementation. These diagnostic metrics should not be improved by changing test labels, the corpus snapshot, or qrels.

## Compare And Gate

Run the same data through `TEXT`, `VECTOR`, `HYBRID`, and `HYBRID+Graph`:

```bash
docker compose up -d --build
EVAL_REVISION="$(git rev-parse HEAD)" docker compose exec -e EVAL_REVISION \
  kb-eval-api python /app/eval/run_experiment_matrix.py --bootstrap --split test
```

The matrix writes per-path Markdown and JSON payloads plus `reports/challenge_matrix.md`. JSON payloads contain the dataset checksum, retrieval configuration, and metrics, so a candidate run can be checked against an accepted baseline:

```bash
docker compose exec kb-eval-api python /app/eval/quality_gate.py \
  --baseline /app/eval/reports/challenge_hybrid_graph.json \
  --candidate /app/eval/reports/candidate_hybrid_graph.json
```

The default gate allows small documented movement (`Recall@5`, `Precision@3`, `nDCG@5`, no-answer rate, citation coverage, extractive citation faithfulness, extractive claim faithfulness, answer correctness, citation correctness, and citation completeness: 5 points; `MRR@10`: 0.03) but rejects larger regressions or a changed dataset checksum. Metrics not applicable to an endpoint are skipped, so run the gate on like-for-like `/search` or `/ask` payloads.

The accepted test matrix is stored in `reports/challenge_matrix.md`. Its JSON payload must contain matching dataset, qrels, split-manifest, corpus-manifest, runtime configuration, and source-revision provenance before it is compared by the quality gate.

`run_experiment_matrix.py` also writes `reports/challenge_hybrid_graph_bootstrap.md`. It reports a paired, non-parametric bootstrap 95% confidence interval for HYBRID+Graph minus HYBRID on the same test cases. A confidence interval spanning zero is not evidence of a reliable graph ranking improvement.

## Run

From the `demo` directory, use `dev` while selecting configuration changes:

```bash
docker compose exec kb-eval-api python /app/eval/run_retrieval_eval.py \
  --bootstrap \
  --mode HYBRID \
  --split dev \
  --output /app/eval/reports/dev_hybrid.md
```
