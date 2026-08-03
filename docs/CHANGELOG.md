# Change Log

This file records project delivery commits with the date and the completed work. Add a new entry whenever a project change is pushed.

## 2026-08-04 00:06 AEST

- Added a source-grounded OpenSearch evidence graph with document-to-chunk, next-chunk, and shared-entity edges.
- Added conditional graph routing for relationship queries and returned inspectable graph paths with file and chunk provenance.
- Added graph helper coverage and entity-validated `Graph evidence coverage` to the retrieval evaluation report.
- Completed the Docker HYBRID graph baseline on 20 cases: `Recall@3=100%`, `Recall@5=100%`, `MRR@10=1.000`, `Positive answer rate=100%`, `Negative no-answer rate=100%`, and `Graph evidence coverage=100%`.

## 2026-08-02 23:45 AEST

- Added an evidence-gated `ANSWER` / `NO_ANSWER` decision to HYBRID retrieval, using a configurable BM25 evidence threshold after RRF fusion.
- Added decision reason and numeric evidence to search responses; rejected queries now return an empty visible candidate list instead of weakly related chunks.
- Extended the golden set with two out-of-scope benefit queries and added positive-answer, negative-no-answer, and decision-error reporting.
- Completed the Docker HYBRID no-answer baseline on 20 cases: `Recall@3=100%`, `Recall@5=100%`, `MRR@10=1.000`, `Positive answer rate=100%`, and `Negative no-answer rate=100%`.

## 2026-07-31 23:17 AEST

- Added executable `HYBRID` search: BM25 and vector candidates are fused with Reciprocal Rank Fusion (RRF) instead of comparing raw scores.
- Added response-level evidence fields (`textRank`, `vectorRank`, source scores, and `fusionScore`) plus configurable candidate depth and RRF constant.
- Expanded the golden set from 12 to 18 cases with paraphrase, relationship, and negative queries.
- Completed same-set Docker baselines: TEXT `MRR@10=1.000`, VECTOR `MRR@10=0.938`, and HYBRID `MRR@10=1.000`; all three reached `Recall@3=100%` and `Recall@5=100%`.
- Negative no-result rate remains `0.0%` for all modes because this stage does not yet include a no-answer threshold; that is a known follow-up rather than a hidden limitation.
- Added a persistent Hugging Face model cache volume and hybrid fusion smoke coverage.

## 2026-07-31 22:39 AEST

- Real vector retrieval: added a local multilingual embedding provider, OpenSearch `knn_vector` indexing, `mode=VECTOR` search, and vector evaluation support.
- Added vector mapping and embedding smoke coverage without downloading a model in CI.
- Completed the Docker-run VECTOR baseline: `Recall@3=100%`, `Recall@5=100%`, and `MRR@10=0.955` on the fixed 12-case dataset.
- Added this change log as the delivery record for future pushes.

## 2026-07-28

- Recorded the Docker-run BM25 retrieval baseline report with `Recall@3`, `Recall@5`, `MRR@10`, and negative-query results.

## 2026-07-27

- Added a fixed retrieval evaluation set, fixture documents, evaluation script, report generation, and CI validation.

## 2026-07-26

- Documented the Evidence-First Graph-Hybrid RAG direction: conditional graph routing, source-grounded graph relations, and controlled improvement.

## 2026-07-24

- Stabilized text retrieval with safe reindex deletion, upload validation, structured search results, smoke tests, and CI.

## 2026-07-23

- Added the initial RAG upgrade plan and documented TEXT, VECTOR, and HYBRID design goals.
