# TabIntelligence -- System Architecture

This document provides a comprehensive visual overview of the TabIntelligence Excel Model Intelligence Platform. The diagrams below cover the full system topology, extraction pipeline lifecycle, database schema, quality scoring methodology, and canonical taxonomy hierarchy. Together they serve as the authoritative architecture reference for engineering, product, and stakeholder audiences.

---

## 1. System Architecture

The platform follows a four-tier architecture with asynchronous extraction workers, an external AI integration layer, and a full observability stack. Users interact through a lightweight SPA frontend; all heavy computation is offloaded to Celery workers that orchestrate multi-stage Claude AI calls.

```mermaid
graph TB
    subgraph Users["Users"]
        CA["Credit Analyst"]
        PM["Portfolio Manager"]
        FDT["Financial Data Team"]
    end

    subgraph Frontend["Frontend Tier"]
        WEB["Web Application<br/><i>Vanilla JS SPA</i><br/><i>Meridian Design System</i>"]
    end

    subgraph Backend["Backend Tier"]
        API["FastAPI REST API<br/><i>50+ endpoints</i><br/><i>Rate limiting &middot; Auth</i>"]
        CELERY["Celery Workers<br/><i>Async extraction</i><br/><i>Dead Letter Queue</i>"]
    end

    subgraph Infrastructure["Infrastructure Tier"]
        PG["PostgreSQL 15<br/><i>15+ tables</i>"]
        REDIS["Redis 7<br/><i>Cache + Broker</i>"]
        S3["S3 / MinIO<br/><i>File Storage</i>"]
    end

    subgraph External["External AI"]
        CLAUDE["Claude AI<br/><i>Anthropic API</i><br/><i>Parse &middot; Triage &middot; Map</i>"]
    end

    subgraph Monitoring["Observability"]
        PROM["Prometheus<br/><i>Metrics scraping</i>"]
        GRAF["Grafana<br/><i>Dashboards</i>"]
        JAEG["Jaeger<br/><i>Distributed tracing</i>"]
    end

    CA --> WEB
    PM --> WEB
    FDT --> WEB

    WEB -->|"HTTPS REST"| API

    API -->|"Read/Write"| PG
    API -->|"Cache lookups"| REDIS
    API -->|"Enqueue tasks"| REDIS

    CELERY -->|"Consume tasks"| REDIS
    CELERY -->|"Read/Write"| PG
    CELERY -->|"Download/Upload"| S3
    CELERY <-->|"AI extraction calls"| CLAUDE

    PROM -->|"Scrape /metrics"| API
    GRAF -->|"Query"| PROM
    API -->|"Traces"| JAEG

    style Users fill:#e8f4fd,stroke:#2196F3,stroke-width:2px
    style Frontend fill:#fff3e0,stroke:#FF9800,stroke-width:2px
    style Backend fill:#e8f5e9,stroke:#4CAF50,stroke-width:2px
    style Infrastructure fill:#fce4ec,stroke:#E91E63,stroke-width:2px
    style External fill:#f3e5f5,stroke:#9C27B0,stroke-width:2px
    style Monitoring fill:#e0f2f1,stroke:#009688,stroke-width:2px
```

---

## 2. Extraction Pipeline

The extraction lifecycle is a five-stage pipeline mixing Claude AI calls with deterministic validation. The pipeline supports checkpoint/resume from any stage, content-hash deduplication, and progress polling for the frontend.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI API
    participant DB as PostgreSQL
    participant S3 as S3 / MinIO
    participant Q as Redis Queue
    participant Worker as Celery Worker
    participant Claude as Claude AI

    User->>API: POST /files/upload (.xlsx)
    Note over API: Content hash deduplication check
    API->>S3: Store Excel file
    API->>DB: Create File + ExtractionJob (status=pending)
    API->>Q: Enqueue extraction task
    API-->>User: 202 Accepted {job_id}

    Note over User,API: Progress polling every 2-15s

    Q->>Worker: Deliver task
    Worker->>S3: Download Excel file
    Worker->>DB: Update status=processing

    rect rgb(232, 245, 233)
        Note over Worker,Claude: Stage 1 -- Parse
        Worker->>Claude: Send Excel content (cells, formulas, formatting)
        Claude-->>Worker: ParsedModel (sheets, cells, dependency graph)
        Worker->>DB: Store lineage event (stage=parsing)
    end

    rect rgb(227, 242, 253)
        Note over Worker,Claude: Stage 2 -- Triage
        Worker->>Claude: Send parsed sheets for classification
        Claude-->>Worker: TriageResult (tier per sheet, skip/process)
        Worker->>DB: Store lineage event (stage=triage)
    end

    rect rgb(255, 243, 224)
        Note over Worker,Claude: Stage 3 -- Map
        Worker->>DB: Check EntityPatterns for shortcircuit
        Note over Worker: High-confidence patterns (>=0.95) bypass Claude
        Worker->>Claude: Send remaining unmapped items
        Claude-->>Worker: MappedItems (canonical_name, confidence, reasoning)
        Worker->>DB: Store lineage event (stage=mapping)
    end

    rect rgb(252, 228, 236)
        Note over Worker: Stage 4 -- Validate (deterministic, no Claude)
        Worker->>Worker: Run accounting identity checks
        Worker->>Worker: Cross-period consistency validation
        Worker->>Worker: Compute quality dimensions
        Worker->>DB: Store lineage event (stage=validation)
    end

    rect rgb(243, 229, 245)
        Note over Worker,Claude: Stage 5 -- Enhanced Map
        Worker->>Claude: Re-send low-confidence items with extra context
        Claude-->>Worker: EnhancedItems (improved mappings + reasoning)
        Worker->>DB: Store lineage event (stage=enhanced_mapping)
    end

    Note over Worker: Checkpoint/resume supported from any stage

    Worker->>DB: Store ExtractionFacts (one row per canonical+period)
    Worker->>DB: Store/update EntityPatterns (learned mappings)
    Worker->>DB: Update ExtractionJob (status=completed, quality_grade)

    User->>API: GET /jobs/{job_id}
    API->>DB: Fetch job status + results
    API-->>User: 200 OK {status, results, quality_grade, line_items}
```

---

## 3. Database Entity Relationship Diagram

The database schema comprises 17 tables covering entities, taxonomy governance, extraction results, audit compliance, and operational concerns (DLQ, FX cache, quality snapshots). Relationships enforce referential integrity with cascading deletes where appropriate.

```mermaid
erDiagram
    Entity {
        UUID id PK
        string name
        string industry
        int fiscal_year_end
        string default_currency
        string reporting_standard
        datetime created_at
    }

    File {
        UUID file_id PK
        string filename
        int file_size
        string s3_key
        string content_hash UK
        UUID entity_id FK
        datetime uploaded_at
    }

    ExtractionJob {
        UUID job_id PK
        UUID file_id FK
        enum status
        string current_stage
        int progress_percent
        json result
        string error
        int tokens_used
        float cost_usd
        string quality_grade
        string taxonomy_version
        datetime created_at
        datetime updated_at
    }

    ExtractionFact {
        UUID id PK
        UUID job_id FK
        UUID entity_id FK
        string canonical_name
        string original_label
        string period
        decimal value
        float confidence
        string sheet_name
        string mapping_method
        string taxonomy_category
        boolean validation_passed
        string currency_code
        datetime created_at
    }

    Taxonomy {
        UUID id PK
        string canonical_name UK
        string category
        string display_name
        json aliases
        text definition
        string typical_sign
        string parent_canonical
        json validation_rules
        boolean deprecated
        string deprecated_redirect
        datetime created_at
    }

    EntityPattern {
        UUID id PK
        UUID entity_id FK
        string original_label
        string canonical_name
        decimal confidence
        int occurrence_count
        boolean is_active
        string created_by
        datetime created_at
    }

    LearnedAlias {
        UUID id PK
        string canonical_name
        string alias_text
        int occurrence_count
        json source_entities
        boolean promoted
        boolean archived
        datetime created_at
    }

    LineageEvent {
        UUID event_id PK
        UUID job_id FK
        string stage_name
        datetime timestamp
        json data
    }

    AuditLog {
        UUID id PK
        datetime timestamp
        string action
        string resource_type
        UUID resource_id
        UUID api_key_id FK
        string ip_address
        json details
        int status_code
    }

    CorrectionHistory {
        UUID id PK
        UUID job_id FK
        UUID entity_id FK
        string original_label
        string old_canonical_name
        string new_canonical_name
        float old_confidence
        float new_confidence
        boolean reverted
        datetime created_at
    }

    APIKey {
        UUID id PK
        string key_hash UK
        string name
        UUID entity_id FK
        boolean is_active
        int rate_limit_per_minute
        datetime created_at
        datetime last_used_at
        datetime expires_at
    }

    TaxonomySuggestion {
        UUID id PK
        string suggestion_type
        string canonical_name
        string suggested_text
        int evidence_count
        json evidence_jobs
        string status
        datetime created_at
        datetime resolved_at
    }

    TaxonomyChangelog {
        UUID id PK
        string canonical_name
        string field_name
        text old_value
        text new_value
        string changed_by
        string taxonomy_version
        datetime created_at
    }

    QualitySnapshot {
        UUID id PK
        UUID entity_id FK
        string snapshot_date
        float avg_confidence
        string quality_grade
        int total_facts
        int total_jobs
        int unmapped_label_count
        datetime created_at
    }

    FxRateCache {
        UUID id PK
        string from_currency
        string to_currency
        string rate_date
        decimal rate
        string source
        datetime fetched_at
    }

    UnmappedLabelAggregate {
        UUID id PK
        string label_normalized
        json original_labels
        UUID entity_id FK
        int occurrence_count
        UUID last_seen_job_id
        json sheet_names
        datetime created_at
    }

    DLQEntry {
        UUID dlq_id PK
        string task_id
        string task_name
        json task_args
        text error
        text traceback
        int replayed
        datetime created_at
    }

    TaxonomyVersion {
        UUID id PK
        string version
        int item_count
        string checksum
        json categories
        datetime applied_at
        string applied_by
    }

    Entity ||--o{ File : "has many"
    Entity ||--o{ EntityPattern : "has many"
    Entity ||--o{ APIKey : "has many"
    Entity ||--o{ QualitySnapshot : "has many"
    Entity ||--o{ UnmappedLabelAggregate : "has many"
    File ||--o{ ExtractionJob : "has many"
    ExtractionJob ||--o{ ExtractionFact : "has many"
    ExtractionJob ||--o{ LineageEvent : "has many"
    ExtractionJob ||--o{ CorrectionHistory : "has many"
    Taxonomy ||--o{ LearnedAlias : "has many aliases"
    APIKey }o--|| Entity : "scoped to"
    AuditLog }o--o| APIKey : "performed by"
```

---

## 4. Quality Scoring System

Each extraction job receives a composite quality grade derived from five weighted dimensions. The weighted average maps to a letter grade that communicates trustworthiness to credit analysts at a glance.

```mermaid
flowchart LR
    MC["Mapping Confidence<br/><b>25%</b>"]
    VS["Validation Success<br/><b>20%</b>"]
    CO["Completeness<br/><b>20%</b>"]
    TS["Time-Series Consistency<br/><b>15%</b>"]
    CR["Cell Reconciliation<br/><b>20%</b>"]

    WA{{"Weighted<br/>Average"}}

    MC --> WA
    VS --> WA
    CO --> WA
    TS --> WA
    CR --> WA

    DEC{"Score<br/>Threshold"}

    WA --> DEC

    GA["Grade A<br/><i>Trustworthy</i><br/>Score >= 90%"]
    GB["Grade B<br/><i>Reliable</i><br/>Score >= 75%"]
    GC["Grade C<br/><i>Needs Review</i><br/>Score >= 60%"]
    GD["Grade D<br/><i>Low Confidence</i><br/>Score >= 40%"]
    GF["Grade F<br/><i>Unreliable</i><br/>Score < 40%"]

    DEC -->|">= 90%"| GA
    DEC -->|">= 75%"| GB
    DEC -->|">= 60%"| GC
    DEC -->|">= 40%"| GD
    DEC -->|"< 40%"| GF

    style MC fill:#c8e6c9,stroke:#388E3C
    style VS fill:#bbdefb,stroke:#1976D2
    style CO fill:#fff9c4,stroke:#FBC02D
    style TS fill:#d1c4e9,stroke:#7B1FA2
    style CR fill:#ffccbc,stroke:#E64A19
    style GA fill:#a5d6a7,stroke:#2E7D32,stroke-width:2px
    style GB fill:#90caf9,stroke:#1565C0,stroke-width:2px
    style GC fill:#fff176,stroke:#F9A825,stroke-width:2px
    style GD fill:#ffab91,stroke:#D84315,stroke-width:2px
    style GF fill:#ef9a9a,stroke:#C62828,stroke-width:2px
```

---

## 5. Taxonomy Hierarchy

The canonical taxonomy contains 312 standardized financial line items organized into six top-level categories. Each category covers a specific domain of financial analysis, from traditional income statement items through specialized project finance metrics.

```mermaid
mindmap
  root(("TabIntelligence Canonical Taxonomy<br/>312 Items"))
    Income Statement -- 54
      Revenue
      COGS
      Gross Profit
      Operating Expenses
      EBITDA
      EBIT
      EBT
      Tax Expense
      Net Income
    Balance Sheet -- 73
      Current Assets
      Non-Current Assets
      Total Assets
      Current Liabilities
      Long-term Debt
      Total Liabilities
      Total Equity
    Cash Flow -- 50
      Operating CF
      Investing CF
      Financing CF
      Free Cash Flow
      Net Change in Cash
    Debt Schedule -- 29
      Total Debt
      Interest Expense
      Principal Payments
      DSCR
      Debt Service
    Metrics -- 93
      Gross Margin
      EBITDA Margin
      ROE
      ROA
      Current Ratio
      Leverage Ratio
      EV/EBITDA
    Project Finance -- 13
      CFADS
      DSRA
      LLCR
      PLCR
      IRR
```

---

*Document generated for the TabIntelligence Excel Model Intelligence Platform documentation package.*
