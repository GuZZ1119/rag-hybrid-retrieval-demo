# Evidence-First Graph-Hybrid Architecture

This demo is a focused RAG service for enterprise-file lookup. It intentionally keeps one OpenSearch deployment for text, vector, and source-grounded graph evidence rather than introducing an additional graph database in v1.

```mermaid
flowchart LR
    U["Enterprise files"] --> I["Upload and extract"]
    I --> C["Clean and chunk"]
    C --> B["BM25 chunk index"]
    C --> V["Vector chunk index"]
    C --> G["Evidence graph index\nDocument - Chunk - Entity"]

    Q["User query"] --> T["BM25 retrieval"]
    Q --> E["Embed query"] --> K["k-NN retrieval"]
    T --> F["RRF fusion"]
    K --> F
    F --> R{"Relationship cue or\ncandidate disagreement?"}
    R -->|"No"| D["Evidence gate"]
    R -->|"Yes"| X["Expand source-grounded\nentity paths"]
    G --> X
    X --> S["Resolve original chunks\nand add low-weight graph evidence"]
    S --> D
    D -->|"Weak evidence"| N["NO_ANSWER"]
    D -->|"Grounded evidence"| A["Citation-first answer"]
```

## Evidence Responsibilities

- **BM25** handles exact enterprise terms, codes, and policy wording.
- **Vector retrieval** handles paraphrases and semantically similar questions.
- **Evidence graph** handles source-traceable relationships across chunks. It never generates a fact from a graph edge alone.

Graph expansion is conditional. Normal keyword questions avoid graph-query cost when BM25 and vector candidates agree. Relationship-oriented or disagreement queries can expand shared entities, then resolve every graph target back to an original chunk before it can influence ranking.

## Quality Loop

```mermaid
flowchart LR
    A["Ask event"] --> L["Privacy-minimized telemetry"]
    F["UP or DOWN feedback"] --> Q["Review queue"]
    N["NO_ANSWER event"] --> Q
    L --> Q
    Q --> H["Human review"]
    H --> G["Golden-set candidate"]
    G --> E["Experiment matrix"]
    E --> C["Quality gate"]
    C -->|"Pass"| M["Accept configuration change"]
    C -->|"Fail"| H
```

This is controlled improvement, not autonomous model mutation. Feedback and weak-evidence events become reviewable test candidates; a configuration change is accepted only after a comparable experiment passes the regression gate.
