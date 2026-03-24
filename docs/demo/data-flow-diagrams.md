# DebtFund — Data Flow & Integration Diagrams

> Detailed data transformation, learning loop, security, and deployment diagrams for the DebtFund platform.

---

## 1. Complete Data Lifecycle

Every Excel file goes through a deterministic transformation chain. Each stage produces typed output that feeds the next.

```mermaid
flowchart TD
    XLSX["📄 Excel File (.xlsx)"]
    RAW["Raw Cells + Formulas + Formatting"]
    PARSED["ParsedModel\nsheets · cells · dependency graph"]
    TRIAGED["TriageResult\ntier per sheet · skip/process decisions"]
    MAPPED["MappedItems\ncanonical_name · confidence · reasoning"]
    VALIDATED["ValidationResult\naccounting checks · quality flags"]
    ENHANCED["EnhancedItems\nre-mapped low-confidence items · quality grade"]

    FACTS[("ExtractionFact\none row per canonical × period")]
    PATTERNS[("EntityPattern\nlearned label → canonical mappings")]
    LINEAGE[("LineageEvent\nstage-by-stage audit trail")]

    XLSX -->|"openpyxl"| RAW
    RAW -->|"Claude AI · Stage 1"| PARSED
    PARSED -->|"Claude AI · Stage 2"| TRIAGED
    TRIAGED -->|"Claude AI · Stage 3"| MAPPED
    MAPPED -->|"Deterministic · Stage 4"| VALIDATED
    VALIDATED -->|"Claude AI · Stage 5"| ENHANCED

    ENHANCED --> FACTS
    ENHANCED --> PATTERNS
    ENHANCED --> LINEAGE

    style XLSX fill:#F0EDE8,stroke:#6B7280
    style ENHANCED fill:#E6F4ED,stroke:#1A7A4A
    style FACTS fill:#E3EEF8,stroke:#1D6B9F
    style PATTERNS fill:#E3EEF8,stroke:#1D6B9F
    style LINEAGE fill:#E3EEF8,stroke:#1D6B9F
```

---

## 2. Entity Learning Feedback Loop

The platform gets smarter with every extraction. Entity patterns create a compounding data asset that reduces Claude API calls and improves accuracy over time.

```mermaid
flowchart LR
    UPLOAD["New Upload\n.xlsx file"]
    EXTRACT["Extraction\nPipeline"]
    CACHE["EntityPattern\nTable"]
    RESULT["Extraction\nResult"]
    REVIEW["User Reviews\n& Corrects"]
    CORRECT["Corrections\nAPI"]
    SUGGEST["Suggestion\nEngine"]
    TAXONOMY["Canonical\nTaxonomy"]
    ALIAS["LearnedAlias\nTable"]

    UPLOAD --> EXTRACT
    CACHE -->|"shortcircuit\n≥ 0.95 confidence"| EXTRACT
    EXTRACT -->|"creates new\npatterns"| CACHE
    EXTRACT --> RESULT
    RESULT --> REVIEW
    REVIEW --> CORRECT
    CORRECT -->|"creates\npatterns"| CACHE
    EXTRACT -->|"discovers\naliases"| ALIAS
    ALIAS -->|"auto-promote\n5+ occurrences\n3+ entities"| TAXONOMY
    SUGGEST -->|"accepted"| TAXONOMY

    style CACHE fill:#E3EEF8,stroke:#1D6B9F,stroke-width:2px
    style TAXONOMY fill:#E6F4ED,stroke:#1A7A4A,stroke-width:2px
```

**Compounding improvement:**

| Extraction # | Pattern Cache | Shortcircuit Rate | Claude API Calls |
|:---:|:---:|:---:|:---:|
| 1st | Empty | 0% | 100% of labels |
| 3rd | ~40 patterns | ~40% | 60% of labels |
| 10th | ~120 patterns | ~70% | 30% of labels |
| 20th+ | ~200 patterns | ~85% | 15% of labels |

---

## 3. Security & Authentication Flow

Every request goes through five middleware layers before reaching the route handler. All significant actions are audit-logged.

```mermaid
sequenceDiagram
    actor Client
    participant MW as Middleware Stack
    participant Auth as Auth Layer
    participant DB as PostgreSQL
    participant Handler as Route Handler
    participant Audit as Audit Log

    Client->>MW: Request + Authorization: Bearer {key}

    Note over MW: 1. RequestIDMiddleware\nassigns X-Request-ID

    Note over MW: 2. SecurityHeadersMiddleware\nHSTS · X-Content-Type-Options\nX-Frame-Options · CSP

    Note over MW: 3. MetricsMiddleware\nrecords request start

    MW->>Auth: 4. RateLimiter check
    alt Rate limit exceeded
        Auth-->>Client: 429 Too Many Requests
    end

    Auth->>DB: 5. SHA-256 hash lookup in api_keys
    DB-->>Auth: APIKey record

    Note over Auth: Check is_active\nCheck expires_at\nUpdate last_used_at

    alt Entity-scoped key
        Auth->>Auth: Verify resource belongs to entity_id
    end

    Auth->>Handler: Authenticated request + APIKey context

    Handler->>DB: Business logic (read/write)
    Handler-->>MW: Response

    MW->>Audit: Log action, resource, api_key_id, IP, user_agent
    MW-->>Client: Response + security headers + X-Request-ID
```

---

## 4. Deployment Architecture

Full Docker Compose topology with Kubernetes-ready health probes.

```mermaid
graph TB
    subgraph Application["Application Layer"]
        API["FastAPI API Server\nPort 8000\n50+ endpoints"]
        WORKER["Celery Worker\nAsync extraction\n5-stage pipeline"]
    end

    subgraph Data["Data Layer"]
        PG[("PostgreSQL 15\nPort 5432\n17 tables")]
        REDIS[("Redis 7\nPort 6379\nCache + Broker")]
        MINIO[("MinIO / S3\nPort 9000\nFile Storage")]
    end

    subgraph Observability["Observability Stack"]
        PROM["Prometheus\nPort 9090\nMetrics scraping"]
        GRAF["Grafana\nPort 3000\nDashboards"]
        JAEGER["Jaeger\nPort 16686\nDistributed tracing"]
    end

    subgraph Health["Health Probes (K8s Ready)"]
        LIVE["/health/live\nLiveness"]
        READY["/health/ready\nReadiness"]
        DBHEALTH["/health/db\nDatabase + Circuit Breaker"]
    end

    API <-->|"SQL"| PG
    API <-->|"Cache"| REDIS
    WORKER <-->|"Task queue"| REDIS
    WORKER <-->|"SQL"| PG
    WORKER <-->|"Files"| MINIO

    PROM -->|"Scrape /metrics"| API
    GRAF -->|"Query"| PROM
    API -->|"Send spans"| JAEGER

    API --- LIVE
    API --- READY
    API --- DBHEALTH

    style Application fill:#E3EEF8,stroke:#1D6B9F,stroke-width:2px
    style Data fill:#E6F4ED,stroke:#1A7A4A,stroke-width:2px
    style Observability fill:#FEF3CD,stroke:#C47D00,stroke-width:2px
    style Health fill:#F0EDE8,stroke:#6B7280,stroke-width:2px
```

**Docker Compose services:**

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| `api` | debtfund:api | 8000 | FastAPI REST server + static frontend |
| `worker` | debtfund:worker | — | Celery async extraction |
| `postgres` | postgres:15 | 5432 | Primary database |
| `redis` | redis:7 | 6379 | Cache + message broker |
| `minio` | minio/minio | 9000, 9001 | S3-compatible file storage |
| `prometheus` | prom/prometheus | 9090 | Metrics collection |
| `grafana` | grafana/grafana | 3000 | Monitoring dashboards |
| `jaeger` | jaegertracing/all-in-one | 16686 | Distributed tracing UI |

---

*Document generated for the DebtFund Excel Model Intelligence Platform documentation package.*
