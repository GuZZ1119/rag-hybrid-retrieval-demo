# RAG Upgrade Plan

## 1. Project Scenario

This project should be upgraded as a small but complete RAG system for an enterprise-file agent.

The target scenario is not a general RAG platform. It is a focused knowledge retrieval service where an agent receives a user keyword or question, searches uploaded enterprise documents, and returns grounded information with source chunks. Typical files include internal manuals, product notes, FAQ files, operation guides, policy snippets, and other text-heavy knowledge documents.

The expected final behavior is:

1. Users upload or register files.
2. The system parses, cleans, chunks, and indexes the documents.
3. A user query can be searched through keyword retrieval, vector retrieval, or hybrid retrieval.
4. The system returns ranked chunks and, when enabled, a RAG answer with citations.
5. Retrieval quality can be backtested with a fixed evaluation set before and after each retrieval change.

The project should remain suitable for a personal portfolio project. It should not try to become Dify, RAGFlow, LlamaIndex, or Haystack. Instead, it should borrow their core RAG ideas and implement the minimum complete path for this project's scenario.

## 2. Current Problems

### 2.1 VECTOR and HYBRID are not real retrieval paths yet

The current demo has `TEXT`, `VECTOR`, and `HYBRID` index modes, but the vector path is still a stub. It proves the dispatch design, but it does not yet generate embeddings, store vectors, run vector search, or merge text and vector results.

Current gap:

- `VECTOR` rebuild does not call an embedding model.
- No vector field exists in the OpenSearch index mapping.
- No vector search endpoint or search branch exists.
- `HYBRID` does not combine BM25 and vector retrieval.

### 2.2 The project is retrieval-only, not full RAG yet

The current `/search` endpoint returns matching chunks. This is useful, but a complete RAG flow also needs an answer step:

- retrieve context,
- build a prompt,
- generate an answer,
- attach citations,
- refuse or say "not found" when evidence is weak.

For this project, the answer step should be simple and source-grounded. It does not need complex agent planning.

### 2.3 Chunking is too basic for reliable retrieval

The current chunking strategy uses fixed character windows with overlap. It is easy to understand, but it can split useful knowledge across boundaries.

Missing pieces:

- paragraph-aware splitting,
- stable chunk metadata,
- source location fields,
- configurable chunk size and overlap per rebuild,
- enough metadata to explain why a result was returned.

### 2.4 Reindexing may leave stale chunks

The current text reindex path upserts chunks by stable chunk id. This prevents duplicate ids, but if a document becomes shorter or chunking parameters change, old chunks with higher indexes may remain unless they are deleted first.

This affects backtesting because evaluation results may include stale evidence.

### 2.5 No backtesting or retrieval quality baseline

The project currently cannot answer:

- Did hybrid retrieval improve over BM25?
- Which queries fail?
- Did a chunking change hurt recall?
- Are expected source chunks appearing in the top results?

This is the most important missing part for a portfolio-ready RAG project. The project needs a small fixed evaluation set and a repeatable script that reports retrieval metrics.

### 2.6 The runnable demo and sanitized Java reference are not clearly separated

The Python demo is runnable. The sanitized Java code shows useful business design, such as knowledge-base models, file/chunk/job concepts, and vector-service integration. But the Java code is not a complete runnable project.

The README and future documentation should be clear about this split:

- `demo/`: runnable local RAG demo.
- `src_sanitized/`: sanitized reference from the internship project.

## 3. Upgrade Goals

### 3.1 Functional goals

The upgraded project should support:

- file upload and indexing,
- text extraction for common file types,
- BM25 text retrieval,
- real vector indexing and vector retrieval,
- hybrid retrieval with explainable score fusion,
- optional reranking,
- answer generation with citations,
- no-answer behavior when retrieved evidence is weak.

### 3.2 Backtesting goals

The project should include a repeatable evaluation workflow.

Core retrieval metrics:

- `Recall@3`: whether expected evidence appears in the top 3 chunks.
- `Recall@5`: whether expected evidence appears in the top 5 chunks.
- `MRR`: whether expected evidence appears near the top.
- `Precision@K`: how much of the returned context is useful.

Optional answer metrics:

- citation coverage,
- answer groundedness,
- no-answer accuracy for questions not covered by the corpus.

Initial target:

- BM25 gets a visible baseline.
- Hybrid should improve or match BM25 on `Recall@5`.
- Retrieval changes should not reduce `Recall@5` by more than 5 percentage points without explanation.
- The README should show the latest backtest command and a small result table.

### 3.3 Scope control

To keep the project achievable:

- Use OpenSearch for both BM25 and vector search first.
- Do not introduce a separate vector database until the OpenSearch path is complete.
- Keep the first evaluation set small, around 20 to 50 questions.
- Keep LLM answer generation optional through environment variables.
- Prefer transparent code over a heavy framework wrapper.

## 4. Reference Points from Other RAG Projects

These projects are useful references, but this project should only adopt the parts that match the scenario.

Reference links:

- RAGFlow: https://github.com/infiniflow/ragflow
- Dify: https://github.com/langgenius/dify
- LlamaIndex: https://github.com/run-llama/llama_index
- Haystack: https://github.com/deepset-ai/haystack

### RAGFlow

Useful reference points:

- document understanding quality matters before retrieval quality,
- chunking should be explainable,
- grounded citations are important for reducing hallucinations,
- retrieval tests and source tracing make the system trustworthy.

What to adopt here:

- better document/chunk metadata,
- citation-first answer output,
- retrieval backtesting.

### Dify

Useful reference points:

- RAG should be a complete pipeline from ingestion to retrieval to application output,
- logs and evaluation help improve prompts and datasets over time,
- APIs make the RAG system usable by another agent or app.

What to adopt here:

- clean API contracts,
- simple logs for indexing and retrieval,
- a documented end-to-end flow.

### LlamaIndex

Useful reference points:

- separate ingestion, indexing, retrieval, query, and generation concepts,
- allow different retrievers and rerankers to be swapped,
- expose enough metadata for source-aware answers.

What to adopt here:

- split the current single-file demo into small modules,
- keep retriever implementations replaceable,
- return structured retrieval results.

### Haystack

Useful reference points:

- retrieval, routing, ranking, and generation should be explicit pipeline steps,
- each step should be testable on its own.

What to adopt here:

- keep the pipeline simple but visible,
- add tests and evaluation around retrieval before adding more features.

## 5. Ordered Implementation Plan

### Phase 1: Stabilize the current text retrieval demo

Goal: make the existing BM25 demo correct and measurable.

Tasks:

1. Fix file-level reindexing so old chunks are deleted before new chunks are inserted.
2. Return `chunkId`, `rank`, `score`, `fileId`, `filename`, and full `content` in search results.
3. Validate chunk configuration, especially `CHUNK_SIZE` and `CHUNK_OVERLAP`.
4. Add basic file size and file type checks for uploads.
5. Update README wording so VECTOR and HYBRID are described as planned or partially implemented until the real path exists.

Acceptance:

- Reindexing the same file with different chunk settings does not leave stale chunks.
- `/search` output is useful for evaluation.
- The demo remains runnable with Docker Compose.

### Phase 2: Add retrieval backtesting

Goal: make current BM25 retrieval measurable before changing the retrieval engine.

Tasks:

1. Add `eval/golden_qa.jsonl`.
2. Add `eval/run_retrieval_eval.py`.
3. Define each evaluation item with:
   - `query`,
   - `expected_file`,
   - `expected_terms`,
   - optional `expected_chunk_text`.
4. Compute `Recall@3`, `Recall@5`, `MRR`, and failed-query details.
5. Generate `eval/reports/latest.md`.

Acceptance:

- A single command can run the retrieval backtest.
- The report shows BM25 baseline results.
- Failed queries list the returned chunks and expected evidence.

### Phase 3: Implement real vector retrieval

Goal: replace the vector stub with actual vector indexing and vector search.

Tasks:

1. Add an embedding provider interface.
2. Start with one default embedding option.
3. Add an OpenSearch `knn_vector` field.
4. Store chunk embeddings during rebuild.
5. Add vector search logic.
6. Add `mode=TEXT|VECTOR|HYBRID` to search requests.

Acceptance:

- `VECTOR` mode indexes embeddings and returns vector-ranked chunks.
- Backtesting can compare BM25 and vector retrieval.
- The embedding model and dimension are explicit in config.

### Phase 4: Implement hybrid retrieval

Goal: make keyword and semantic retrieval work together.

Tasks:

1. Run BM25 and vector retrieval as two candidate generators.
2. Merge candidates with Reciprocal Rank Fusion or a simple weighted score.
3. Return debug fields such as `textRank`, `vectorRank`, and `fusionScore`.
4. Tune `topK` and fusion parameters through the eval set.
5. Keep keyword matching strong because the target scenario is enterprise-file lookup by keywords and short questions.

Acceptance:

- `HYBRID` mode produces fused ranked results.
- Hybrid `Recall@5` is equal to or better than BM25 on the evaluation set.
- The report explains where hybrid helps and where it does not.

### Phase 5: Add a simple RAG answer endpoint

Goal: turn retrieval results into grounded answers.

Tasks:

1. Add `/ask`.
2. Retrieve top chunks with HYBRID by default.
3. Build a short prompt using only retrieved context.
4. Return:
   - `answer`,
   - `citations`,
   - `retrievedChunks`,
   - `mode`,
   - confidence or evidence score.
5. Add a no-answer rule when retrieval score is too weak.

Acceptance:

- Answers include citations.
- The system does not invent content when no relevant chunk is found.
- The answer endpoint can be used by an external agent.

### Phase 6: Add lightweight quality gates

Goal: keep the project stable without overbuilding.

Tasks:

1. Add unit tests for chunking and reindex behavior.
2. Add API smoke tests for upload, reindex, search, and eval.
3. Add a GitHub Actions workflow if dependencies remain lightweight.
4. Add a documented command sequence for local validation.

Acceptance:

- A contributor can run tests and eval locally.
- The latest metric table is visible in README or `eval/reports/latest.md`.
- Future retrieval changes are evaluated against the same questions.

## 6. Suggested Milestones

### Milestone 1: Reliable BM25 baseline

Deliverables:

- fixed reindex behavior,
- improved search result schema,
- first golden QA set,
- first BM25 backtest report.

### Milestone 2: Real vector mode

Deliverables:

- embedding provider,
- OpenSearch vector mapping,
- vector indexing,
- vector retrieval,
- BM25 vs vector report.

### Milestone 3: Hybrid retrieval with measurable gain

Deliverables:

- hybrid search,
- fusion score output,
- retrieval comparison table,
- documented cases where hybrid improves keyword-only search.

### Milestone 4: Agent-ready RAG answer

Deliverables:

- `/ask` endpoint,
- citations,
- no-answer behavior,
- short integration example for an enterprise file agent.

## 7. Definition of Done

The project can be considered complete for the current portfolio goal when:

- it can ingest files and rebuild indexes locally,
- it supports TEXT, VECTOR, and HYBRID retrieval as real paths,
- it can answer questions using retrieved evidence,
- answers include citations,
- retrieval backtesting is repeatable,
- the README shows how to run the demo and the backtest,
- the latest report shows Recall@K and MRR for at least BM25 and HYBRID.

## 8. Non-Goals

The project should not try to implement these in the first complete version:

- multi-tenant enterprise admin system,
- complex workflow builder,
- large-scale distributed indexing,
- full observability stack,
- many vector database backends,
- advanced agent planning.

These are valuable in larger products, but they would distract from the main goal: a small, complete, measurable RAG system for enterprise file lookup.
