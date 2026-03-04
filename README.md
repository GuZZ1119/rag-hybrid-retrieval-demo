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
