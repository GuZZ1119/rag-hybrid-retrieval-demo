# Change Log

This file records project delivery commits with the date and the completed work. Add a new entry whenever a project change is pushed.

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
