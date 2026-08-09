# Change Log

This file records project delivery commits with the date and the completed work. Add a new entry whenever a project change is pushed.

## 2026-08-09 23:20 AEST

- Expanded the fixed Golden Set from 20 to 64 labelled cases: 22 keyword, 14 paraphrase, 10 relationship, and 18 negative queries.
- Added realistic challenge fixtures and scenario labels for version conflicts, cross-document evidence, distractors, and multi-condition questions.
- Added scenario validation and report metadata so the challenge mix is visible and reproducible.
- Recorded the first expanded Docker HYBRID ask baseline: `Recall@3=100%`, `Recall@5=100%`, `MRR@10=0.931`, `Negative no-answer rate=16.7%`, and `Graph evidence coverage=40.0%`. These are explicit calibration targets for the next push.

## 2026-08-09 23:20 AEST

- Routed the OpenSearch evidence graph for relationship queries and BM25/vector candidate disagreement, with an explicit route reason and overlap count.
- Resolved graph targets back to original text chunks and included them as a lower-weight third RRF candidate source with `graphRank` provenance, without re-scoring chunks that already have direct evidence.
- Extended privacy-minimized ask telemetry with latency, route metadata, and rank snapshots; added the `GET /feedback/review-queue` endpoint for `NO_ANSWER` and negative-feedback review cases.
- Extended graph evaluation with route-rate and graph-candidate-coverage metrics, and updated smoke coverage and documentation.
- Completed the Docker HYBRID ask baseline on 20 cases with `Recall@3=100%`, `Recall@5=100%`, `MRR@10=1.000`, `Graph route rate=100%` for relationship queries, and `Citation coverage=100%`.

## 2026-08-09 23:11 AEST

- Added privacy-minimized `/ask` event logging, binary feedback submission, and feedback summary aggregation keyed by request ID.
- Updated fixture bootstrap to index distractor documents and added standard/challenge quality slices to evaluation reports.
- Completed the Docker quality baseline on a six-document fixture corpus: overall and challenge `Recall@3=100%`, overall and challenge `MRR@10=1.000`, `Negative no-answer rate=100%`, and `Citation coverage=100%`.

## 2026-08-09 22:17 AEST

- Added `POST /ask`, which composes HYBRID retrieval, evidence gating, graph evidence, and structured citations into a user-facing answer response.
- Added an optional grounded OpenAI-compatible completion adapter with a fully runnable extractive fallback when no external LLM is configured.
- Added citation coverage evaluation and an ask baseline report.
- Completed the Docker HYBRID ask baseline on 20 cases: `Recall@3=100%`, `Recall@5=100%`, `MRR@10=1.000`, `Positive answer rate=100%`, `Negative no-answer rate=100%`, `Graph evidence coverage=100%`, and `Citation coverage=100%`.

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
