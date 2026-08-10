# Three-Minute Demo Script

Run the commands from `demo/`. The first vector run may take longer because it downloads the embedding model; later runs reuse the Docker cache.

## 0:00 - Start The Service

```bash
docker compose up -d --build
curl http://localhost:8080/health
```

State the scenario: this is an enterprise-file retrieval API with keyword, semantic, and conditional relationship evidence.

## 0:20 - Show The Architecture

Open `docs/ARCHITECTURE.md` and explain one sentence per evidence path:

- BM25 protects exact policy terms and codes.
- Vector retrieval handles paraphrase.
- The graph only runs for relationship cues or candidate disagreement and always resolves back to source chunks.

## 0:50 - Show The Measured Comparison

```bash
EVAL_REVISION="$(git rev-parse HEAD)" docker compose exec -e EVAL_REVISION \
  kb-api python /app/eval/run_experiment_matrix.py --bootstrap
cat ../eval/reports/challenge_matrix.md
```

Point out that HYBRID has the best MRR in the current challenge set, while HYBRID+Graph adds relationship evidence without reducing Recall@5 or MRR.

## 1:35 - Ask A Normal Policy Question

```bash
curl -X POST http://localhost:8080/ask \
  -H "Content-Type: application/json" \
  -d '{"q":"采购金额超过五千元需要谁审批？","topK":3}'
```

Show `answer`, `citations`, and the returned ranked chunks. The answer is grounded in the cited source even when no external LLM is configured.

## 2:00 - Show Conditional Graph Evidence

```bash
curl "http://localhost:8080/search?q=报销为什么需要关联采购申请？&mode=HYBRID&graphEnabled=true"
curl "http://localhost:8080/search?q=报销为什么需要关联采购申请？&mode=HYBRID&graphEnabled=false"
```

Compare `graphRouted`, `graphRouteReason`, and `graphEvidence`. Emphasize that disabling graph preserves the hybrid baseline; graph adds traceable relationship evidence only when it is justified.

## 2:30 - Show The Improvement Loop

```bash
curl -X POST http://localhost:8080/ask \
  -H "Content-Type: application/json" \
  -d '{"q":"公司食堂补贴标准是什么？","topK":3}'
curl http://localhost:8080/feedback/review-queue
```

Close with the honest result: the challenge set currently exposes imperfect negative rejection and graph coverage. Those cases enter review, are added to the Golden Set when confirmed, and any fix must pass the regression gate before it is accepted.
