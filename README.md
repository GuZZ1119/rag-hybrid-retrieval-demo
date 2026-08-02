RAG Hybrid Retrieval Demo (Sanitized)
面向 RAG 的混合检索 Demo（脱敏版）

A portfolio-friendly hybrid retrieval demo for RAG-style systems.
This repository demonstrates a document-to-retrieval pipeline with support for full-text indexing, vector-ready design, and hybrid retrieval, designed to be clean, reproducible, and runnable on any machine.

这是一个面向 RAG 场景的混合检索作品集 Demo。
本仓库展示 文档 → 解析 → 分块 → 索引 → 检索（高亮） 的完整闭环，
支持全文索引、向量检索扩展与混合检索设计，目标是做到 干净、可复现、任意新环境一键跑通。

✅ This repository is sanitized / 本仓库已完成脱敏

No private tokens / IPs / passwords / 不包含任何私密 token / IP / 密码

No internal business code / 不包含任何公司内部业务代码

No environment-specific dependencies / 不依赖特定机器/特定环境路径

🚀 What This Demo Shows / 本 Demo 展示内容
Core Pipeline / 核心流程

File upload / 文件上传

Text extraction and cleaning / 文本解析与清洗

Chunking with overlap / 分块（含 overlap）

Full-text indexing / 全文索引

Hybrid retrieval design / 混合检索设计

Search with highlighted results / 支持高亮检索结果

Safe index rebuild and reconstruction / 支持安全索引重建与索引重构

🧩 Indexing Design / 索引设计思想

Chunk-level indexing / 以 chunk（分块）为粒度建索引

Stable chunk IDs for safe rebuild / chunk ID 稳定，支持安全重建

Clear separation between source files and index data / 源文件与索引数据清晰隔离

Retrieval-oriented structure for future RAG workflows / 面向 RAG 工作流的检索结构设计

Index Modes / 索引模式

TEXT / 全文检索

VECTOR / 向量检索

HYBRID / 混合检索

This demo is designed around hybrid indexing.
It supports full-text retrieval directly and is structured to accommodate vector-based retrieval and hybrid retrieval strategies.

本 Demo 以混合索引设计为核心。
当前可直接展示全文检索能力，同时在结构上支持向量检索扩展与混合检索策略。

🧰 Requirements / 运行环境

Docker Desktop

Docker Compose v2

本地无需安装 Java / Python / 数据库
不需要任何既有环境或历史依赖


⚡ Quickstart (One-Command Demo) / 一键启动 Demo
1) Start all services / 启动服务

Step / 步骤：
进入 demo 目录，然后启动容器服务。

Command / 命令：
```
cd demo
docker compose up -d --build
```
This will start / 将启动以下服务：

OpenSearch: http://localhost:9200

OpenSearch Dashboards: http://localhost:5601

Demo KB API: http://localhost:8080

Wait about 20–30 seconds for OpenSearch to be ready.
等待约 20–30 秒，OpenSearch 初始化完成即可。


2) Upload a document / 上传文档

Command / 命令：
```
curl -F "file=@demo.txt" http://localhost:8080/upload
```
Response example / 返回示例：
```
{
"fileId": "69742593-d8a8-450a-a933-78996802aa9d",
"filename": "demo.txt"
}
```

3) Build / rebuild the index / 构建（或重建）索引

Command / 命令：
```
curl -X POST http://localhost:8080/reindex
```
This step will / 此步骤会：

Parse uploaded files / 解析已上传文件

Clean and split text into chunks / 清洗文本并进行分块（含 overlap）

Bulk upsert chunks into OpenSearch / 批量 upsert 写入 OpenSearch

Refresh index for immediate search / 刷新索引以便立刻可搜


4) Search with highlight / 高亮搜索

Command / 命令：
```
curl "http://localhost:8080/search?q=水"
```

Example response / 返回示例：
```
{
"count": 2,
"results": [
{
"filename": "demo.txt",
"chunkIndex": 0,
"highlight": "这里有<em>水</em>。OpenSearch 高亮测试。"
}
]
}
```
5) Index Mode Switching / 索引模式切换

This demo now supports index mode configuration to better reflect real RAG retrieval systems:

TEXT: full-text retrieval via OpenSearch (BM25-style)

VECTOR: vector indexing pipeline (pluggable in demo)

HYBRID: combined workflow (TEXT + VECTOR)

本 Demo 现已支持索引模式配置，更贴近真实 RAG 检索系统：

TEXT：OpenSearch 全文检索（BM25 风格）

VECTOR：向量索引流程（Demo 中为可插拔/占位）

HYBRID：混合流程（TEXT + VECTOR 组合）

API:

GET /index/config — view current index config / 查看当前索引配置

POST /index/config — update indexMode/config / 更新索引模式与配置

Example / 示例（PowerShell 推荐写法）：

Set mode to HYBRID / 设置为 HYBRID：
```
$body = @{ indexMode = "HYBRID" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/index/config
" -ContentType "application/json" -Body $body
```
View config / 查看配置：
```
curl.exe "http://localhost:8080/index/config
```
6) Index Rebuild & Reconstruction Dispatcher / 索引重建与重构分发

A unified rebuild endpoint is provided to reconstruct index state deterministically from source documents.

TEXT: rebuild OpenSearch index entries

VECTOR: trigger vector upsert pipeline (demo placeholder)

HYBRID: execute both steps

提供统一的“索引重构”入口，可基于源文档稳定重建索引状态。

TEXT：重建 OpenSearch 文本索引

VECTOR：触发向量 upsert 流程（Demo 占位）

HYBRID：两者都执行

API:

POST /index/rebuild — rebuild/reconstruct by current indexMode / 按当前 indexMode 执行重建/重构

Optional: ?fileId=xxx to rebuild a single file / 可选参数 fileId，仅重构单个文件

Examples / 示例：

Rebuild by mode / 按模式重构：
```
curl.exe -X POST "http://localhost:8080/index/rebuild
```

Rebuild a single file / 重构单个文件：
```
curl.exe -X POST "http://localhost:8080/index/rebuild?fileId=YOUR_FILE_ID
```

🔄 Index Reconstruction / 索引重构设计说明

This demo supports safe, repeatable, and deterministic index reconstruction.
本 Demo 支持安全、可重复、结果可预测的索引重构。

Why reconstruct the index? / 为什么需要索引重构

The index may need to be rebuilt after deletion or corruption / 索引删除、损坏后需要恢复

Chunking parameters may change / 分块参数可能调整（如 chunk size / overlap）

Retrieval logic may evolve over time / 检索策略可能迭代升级

Useful for debugging, migration, and incremental development / 便于调试、迁移和迭代开发

How reconstruction works / 索引重构如何工作

Each chunk uses a stable ID: fileId:chunkIndex / 每个 chunk 使用稳定 ID：fileId:chunkIndex

Reconstructing the same source overwrites existing indexed chunks / 对同一来源重构时覆盖已有索引数据

No duplicate chunks are created / 不会产生重复 chunk

The operation remains idempotent / 整体操作保持幂等

This mirrors a production-grade retrieval pipeline where index state can be rebuilt safely from source documents.
这对应生产级检索系统中的常见做法：索引状态可以基于源文档安全恢复与重建。

🔀 Hybrid Retrieval Support / 混合检索支持

This project is designed for hybrid retrieval workflows.
The current demo focuses on searchable document indexing while preserving the design needed for combining keyword-based retrieval and vector-based retrieval.

本项目按混合检索工作流进行设计。
当前 Demo 聚焦于可运行的文档索引与搜索闭环，同时保留了关键词检索与向量检索结合所需的结构设计。

Hybrid retrieval design can support:

Keyword-based search / 关键词检索

Vector-based semantic retrieval / 基于语义的向量检索

Combined ranking strategies / 组合式排序策略

Future reranking integration / 后续重排能力扩展

## Retrieval Evaluation / 检索回测

The repository includes a small fixed evaluation set for measuring retrieval changes before vector, hybrid, or graph retrieval is introduced. The current baseline evaluates the `TEXT` search path.

仓库提供一套小型固定题集，用于在引入向量、混合检索或图谱检索前后比较检索质量。当前基线评测的是 `TEXT` 搜索路径。

From the `demo` directory, run:

```bash
docker compose exec kb-api python /app/eval/run_retrieval_eval.py --bootstrap
```

`--bootstrap` uploads any missing fixture documents, rebuilds the selected demo index, runs the fixed golden evaluation cases, and writes the Markdown report to `eval/reports/latest.md`.

The report includes:

- `Recall@3` and `Recall@5` for evidence retrieval,
- `MRR@10` for ranking quality,
- a negative-query no-result rate,
- failed queries with their returned chunks.

Validate the dataset and evaluation logic without starting Docker:

```bash
python eval/run_retrieval_eval.py --validate-only
python eval/eval_smoke_test.py
```

The fixtures are intentionally synthetic and should be used with a clean demo data volume, not a real knowledge base.

## Vector Retrieval / 向量检索

`VECTOR` is a real OpenSearch k-NN retrieval path. It stores normalized chunk embeddings in the separate `kb_demo_chunks_vector_v1` index, so the existing BM25 index remains safe and directly comparable.

`VECTOR` 是真实的 OpenSearch k-NN 检索路径。它将归一化 chunk 向量写入独立的 `kb_demo_chunks_vector_v1` 索引，现有 BM25 索引不会被迁移或覆盖，可以直接对比。

The Docker demo uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` with 384 dimensions on CPU. The first vector rebuild downloads the model; later rebuilds reuse the local model cache.

Docker Demo 默认使用 CPU 上的 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（384 维）。首次向量重建会下载模型，之后会复用本地模型缓存。

From the `demo` directory, rebuild and evaluate vector retrieval:

```bash
docker compose up -d --build
docker compose exec kb-api python /app/eval/run_retrieval_eval.py \
  --bootstrap \
  --mode VECTOR \
  --output /app/eval/reports/vector_baseline.md
```

Search a query directly with either retrieval path:

```bash
curl "http://localhost:8080/search?q=远程访问公司资源需要什么安全措施&mode=TEXT"
curl "http://localhost:8080/search?q=远程访问公司资源需要什么安全措施&mode=VECTOR"
```

`/search` returns `textRank` for TEXT results and `vectorRank` plus `embeddingModel` for VECTOR results.

## Hybrid Retrieval / 混合检索

`HYBRID` retrieves candidates from the BM25 and vector indexes independently, then applies Reciprocal Rank Fusion (RRF): `1 / (rrfK + rank)`. This avoids directly comparing incompatible BM25 and vector scores while rewarding evidence returned by both paths.

`HYBRID` 会先从 BM25 与向量索引独立召回候选，再以 Reciprocal Rank Fusion（RRF，`1 / (rrfK + rank)`）融合排序。这样无需直接比较两种不可互换的原始分数，并会优先保留被两条证据路径同时召回的 chunk。

Run the three baselines against the same golden set:

```bash
docker compose exec kb-api python /app/eval/run_retrieval_eval.py --bootstrap --mode TEXT --output /app/eval/reports/bm25_baseline.md
docker compose exec kb-api python /app/eval/run_retrieval_eval.py --bootstrap --mode VECTOR --output /app/eval/reports/vector_baseline.md
docker compose exec kb-api python /app/eval/run_retrieval_eval.py --bootstrap --mode HYBRID --output /app/eval/reports/hybrid_baseline.md
```

```bash
curl "http://localhost:8080/search?q=采购费用为什么要先走审批再申请报销？&mode=HYBRID"
```

Hybrid results expose `textRank`, `vectorRank`, `textScore`, `vectorScore`, and `fusionScore`; `candidateK` and `rrfK` are returned at the response root. The default values are configurable through `HYBRID_CANDIDATE_K=20` and `HYBRID_RRF_K=60`.

混合结果会返回 `textRank`、`vectorRank`、`textScore`、`vectorScore` 与 `fusionScore`，响应根部还会返回 `candidateK` 和 `rrfK`。默认值可通过 `HYBRID_CANDIDATE_K=20` 和 `HYBRID_RRF_K=60` 调整。

## Evidence-Gated Retrieval / 证据门控检索

The production-oriented `HYBRID` path adds a small, inspectable decision layer after retrieval. A query is returned as `ANSWER` only when at least one fused candidate reaches the configured BM25 evidence threshold. Otherwise the API returns `NO_ANSWER`, clears the candidate list, and exposes the decision reason and numeric evidence instead of presenting a weakly similar document as an answer.

面向生产使用的 `HYBRID` 路径会在检索后增加一个轻量、可检查的决策层。至少一个融合候选达到配置的 BM25 证据阈值时才返回 `ANSWER`；否则 API 返回 `NO_ANSWER`、清空候选列表，并返回判断原因和数值证据，避免把弱语义相似的文档伪装成答案。

`NO_ANSWER_MIN_TEXT_SCORE=4.0` is calibrated against the current fixed golden set and should be re-measured after replacing the demo documents. `TEXT` and `VECTOR` retain their raw retrieval behavior; the gate is deliberately enabled only for the dual-evidence `HYBRID` path.

`NO_ANSWER_MIN_TEXT_SCORE=4.0` 基于当前固定 golden set 校准；替换 Demo 文档后必须重新回测。`TEXT` 与 `VECTOR` 保留原始检索行为，门控仅在双证据 `HYBRID` 路径启用。

```bash
docker compose exec kb-api python /app/eval/run_retrieval_eval.py \
  --bootstrap \
  --mode HYBRID \
  --output /app/eval/reports/no_answer_baseline.md
```

The report adds `Positive answer rate`, `Negative no-answer rate`, and a `Decision Errors` section alongside retrieval metrics.

🧠 Engineering Highlights / 工程亮点

Hybrid indexing design / 混合索引设计

OpenSearch bulk indexing / OpenSearch 批量写入

Chunk-level search with highlight / chunk 粒度检索 + 高亮

Safe index rebuild and reconstruction / 安全索引重建与索引重构

Fully containerized demo / 全容器化可运行

Zero local environment dependency / 本地零环境依赖

This repository focuses on clarity, portability, and retrieval system design, rather than framework or business complexity.
本仓库强调清晰、可移植、可复现的检索系统设计，而非框架堆叠或业务复杂度。

📊 OpenSearch Dashboards / 可视化界面

After startup, visit / 启动后访问：
http://localhost:5601

You can inspect / 你可以查看：

Index mappings / 索引 mapping

Indexed chunks / 已写入的 chunk 文档

Query behavior / 查询与高亮效果

Rebuilt index state / 重建后的索引状态

📦 Project Structure (Demo) / 项目结构（Demo）
```
rag-hybrid-retrieval-demo/

demo/

docker-compose.yml

api/

app.py

Dockerfile

requirements.txt

demo.txt

src_sanitized/ （Sanitized Java / Python code, design reference）

README.md
```
🛡️ Notes / 说明

This repository is intended for portfolio and demo usage.
本仓库用于作品集展示与可运行 Demo。

The full system design includes TEXT, VECTOR, and HYBRID retrieval modes, along with extensible indexing and reconstruction workflows.
完整系统设计包含 TEXT、VECTOR、HYBRID 检索模式，并支持可扩展的索引与重构流程。

This demo focuses on a clean and reproducible retrieval pipeline while preserving a realistic hybrid-retrieval architecture.
本 Demo 聚焦于干净、可复现的检索闭环，同时保留真实混合检索系统的架构设计。

Contributions and issues are welcome.
欢迎提 issue 或 PR。
