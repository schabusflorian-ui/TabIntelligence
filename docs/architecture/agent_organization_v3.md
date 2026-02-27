# Agent Organization v3.0

## Guided Hybrid Architecture

**Core Principle:** We provide structure, rules, and domain expertise. Claude provides reading, understanding, and reasoning. Together = stronger than either alone.

**Team:** 3-4 Engineers over 10-12 weeks

---

## Agent Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRODUCT MANAGER                                    │
│                    Oversight, Quality Gates, Contracts                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│    FOUNDATION     │     │ GUIDED EXTRACTION │     │   USER INTERFACE  │
│    (Weeks 1-3)    │     │   (Weeks 4-8)     │     │   (Weeks 9-12)    │
│                   │     │                   │     │                   │
│  Agent 1: DB      │     │  Agent 3: Orch    │     │  Agent 8: Add-in  │
│  Agent 2: API     │     │  Agent 4: Guide   │     │  Agent 9: Dash    │
│                   │     │  Agent 5: Valid   │     │                   │
│                   │     │  Agent 6: Lineage │     │                   │
│                   │     │  Agent 7: Calib   │     │                   │
└───────────────────┘     └───────────────────┘     └───────────────────┘
```

---

## The 9 Agents

### Foundation Layer

| # | Agent | Responsibility | Criticality | Owner |
|---|-------|----------------|-------------|-------|
| **1** | Database Architect | Schema, migrations, entity patterns | High | Backend #1 |
| **2** | API & Infrastructure | FastAPI, S3, auth, security | High | Backend #1 |

### Guided Extraction Engine

| # | Agent | Responsibility | Criticality | Owner |
|---|-------|----------------|-------------|-------|
| **3** | Extraction Orchestrator | Multi-stage guided extraction | **Critical** | Backend #2 |
| **4** | Guidelines Manager | Prompts, taxonomy, entity patterns | **Critical** | Backend #2 |
| **5** | Validator | Deterministic + guided verification | High | Backend #2 |

### Trust Layer

| # | Agent | Responsibility | Criticality | Owner |
|---|-------|----------------|-------------|-------|
| **6** | Lineage Tracker | Provenance, audit trail | **Existential** | Shared |
| **7** | Confidence Calibrator | Score calibration, thresholds | High | Backend #2 |

### User Interface Layer

| # | Agent | Responsibility | Criticality | Owner |
|---|-------|----------------|-------------|-------|
| **8** | Excel Add-in | Task pane, provenance panel, functions | **Existential** | Full-stack |
| **9** | Review Dashboard | Review queue, corrections, health | High | Full-stack |

---

## Existential Challenges

Two challenges remain make-or-break:

| Challenge | Owner | Target | Governance |
|-----------|-------|--------|------------|
| **Lineage 100%** | Agent 6 | 100% completeness | PR blocking, automated validation |
| **Add-in Adoption** | Agent 8 | Works on all platforms | Weekly cross-platform testing |

**Note:** Mapping accuracy is no longer existential because Claude handles extraction with our guidance. We validate output rather than building the mapping engine.

---

## Core Libraries by Agent

| Agent | Libraries | Purpose |
|-------|-----------|---------|
| **3 (Orchestrator)** | `openpyxl`, `formulas`, `networkx`, `anthropic` | Excel parsing, formula AST, dependency graph, Claude API |
| **4 (Guidelines)** | — | Prompts and taxonomy (no special libs) |
| **5 (Validator)** | `networkx` | Validation graph traversal |
| **6 (Lineage)** | `networkx` | Provenance graph queries |
| **8 (Add-in)** | `Office.js` | Excel integration |
| **9 (Dashboard)** | `React` | Web UI |

### Key Library Details

```python
# formulas - Parse Excel formulas to AST
from formulas import Parser
parser = Parser()
ast = parser.parse("=SUM(A1:A10) + B5")
refs = ast.get_references()  # ['A1:A10', 'B5']

# networkx - Dependency graph for lineage
import networkx as nx
G = nx.DiGraph()
G.add_edge('B5', 'C10')  # C10 depends on B5
ancestors = nx.ancestors(G, 'C10')  # What affects C10?
cycles = list(nx.simple_cycles(G))  # Circular refs
```

### Open Source References

| Resource | Use For |
|----------|---------|
| [LLMExcel](https://github.com/liminityab/LLMExcel) | Add-in architecture patterns |
| [SpreadsheetLLM](https://arxiv.org/abs/2407.09025) | Compression techniques |

---

## Agent Details

### Agent 1: Database Architect

**Mission:** Design and implement the data foundation.

**Key Tables:**
- `entities` — Companies/assets being tracked
- `files` — Uploaded Excel files
- `extractions` — Extraction results
- `line_items` — Individual extracted values
- `mappings` — Label → canonical mappings
- `entity_patterns` — Learned patterns per entity
- `lineage_events` — Full audit trail

**Interfaces:**
- → Agent 3: Extraction storage
- → Agent 4: Entity patterns CRUD
- → Agent 6: Lineage event storage

---

### Agent 2: API & Infrastructure

**Mission:** Build the API layer and infrastructure.

**Key Endpoints:**
```
POST   /api/v1/files/upload           # Upload Excel file
GET    /api/v1/jobs/{job_id}          # Job status
GET    /api/v1/jobs/{job_id}/stream   # SSE progress
GET    /api/v1/extractions/{file_id}  # Extraction results
GET    /api/v1/lineage/{value_id}     # Provenance chain
GET    /api/v1/entities/{id}/metrics  # Query metrics
POST   /api/v1/mappings/{id}/correct  # User correction
GET    /api/v1/review/queue           # Items needing review
```

**Interfaces:**
- → Agent 3: Job queue
- → Agent 8: Add-in API
- → Agent 9: Dashboard API

---

### Agent 3: Extraction Orchestrator

**Mission:** Coordinate multi-stage guided extraction using Claude.

**The 5-Stage Pipeline:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GUIDED EXTRACTION PIPELINE                           │
└─────────────────────────────────────────────────────────────────────────────┘

Stage 1: GUIDED PARSING
├── Input: Raw Excel file bytes
├── Prompt: Cell extraction format, formula capture rules
├── Claude: Reads file, understands context, extracts cells
├── We Add: Dependency graph (deterministic), lineage events
└── Output: ParsedModel

Stage 2: GUIDED TRIAGE
├── Input: ParsedModel (sheet summaries)
├── Prompt: Tier definitions (1-4), skip criteria
├── Claude: Classifies sheets with reasoning
├── We Add: Processing queue, lineage events
└── Output: TriageResult per sheet

Stage 3: GUIDED STRUCTURE
├── Input: Triaged sheets (Tier 1-3 only)
├── Prompt: Section taxonomy, period patterns, hierarchy rules
├── Claude: Identifies sections, periods, hierarchy
├── We Add: Validation, lineage events
└── Output: ModelStructure

Stage 4: GUIDED MAPPING
├── Input: Extracted line items, entity context
├── Prompt: Canonical taxonomy, entity patterns
├── Claude: Maps with reasoning, provides alternatives
├── We Add: Cache updates, lineage events
└── Output: MappingResult per item

Stage 5: VERIFICATION
├── Input: All mapped values
├── Deterministic: BS balance, derivation checks
├── Claude: Explains anomalies, reasons about edge cases
├── We Add: Final confidence, review flags, lineage
└── Output: VerifiedExtraction
```

**Key Responsibilities:**
- Manage Claude API calls (batching, retries, error handling)
- Emit lineage events at each stage
- Track processing time and cost
- Route to human review when confidence is low

**Interfaces:**
- ← Agent 2: Receives jobs from queue
- → Agent 4: Gets prompts and taxonomy
- → Agent 5: Sends for validation
- → Agent 6: Emits lineage events
- → Agent 7: Sends for calibration

**Libraries:**
```python
# Core extraction
import openpyxl                    # Excel read/write
from formulas import Parser        # Formula parsing
import networkx as nx              # Dependency graph
from anthropic import Anthropic    # Claude API

# Formula parsing example
parser = Parser()
ast = parser.parse("=SUM(A1:A10) + B5 * 1.1")
refs = ast.get_references()  # ['A1:A10', 'B5']

# Dependency graph example
G = nx.DiGraph()
for cell, formula in formulas.items():
    for ref in parse_refs(formula):
        G.add_edge(ref, cell)  # ref affects cell
        
# Detect circular references
cycles = list(nx.simple_cycles(G))
if cycles:
    flag_circular_refs(cycles)
```

**Token Compression (SpreadsheetLLM concepts):**
```python
# Instead of sending all cells, compress:
def compress_for_claude(sheet_data):
    return {
        "headers": extract_header_row(sheet_data),
        "structure": [
            {"row": r, "label": l, "bold": b, "indent": i}
            for r, l, b, i in get_labels(sheet_data)
        ],
        # Only send sample values, not all data
        "sample_values": get_first_period_values(sheet_data)
    }
# Reduces tokens by 50-70%
```

---

### Agent 4: Guidelines Manager

**Mission:** Maintain the domain expertise that guides Claude.

**Components:**

```
Guidelines Manager
├── Prompt Templates
│   ├── parsing_prompt.txt
│   ├── triage_prompt.txt
│   ├── structure_prompt.txt
│   ├── mapping_prompt.txt
│   └── verification_prompt.txt
│
├── Canonical Taxonomy
│   ├── income_statement (25+ items)
│   ├── balance_sheet (25+ items)
│   ├── cash_flow (20+ items)
│   ├── debt_schedule (15+ items)
│   └── other (15+ items)
│
├── Entity Patterns
│   ├── Per-entity learned mappings
│   ├── "ThermoStore: 'Net Sales' → revenue"
│   └── Updated from user corrections
│
└── Tier Definitions
    ├── Tier 1: Core statements (P&L, BS, CF)
    ├── Tier 2: Supporting (Debt, D&A, WC)
    ├── Tier 3: Analytical (Assumptions)
    └── Tier 4: Skip (Scratch, Charts)
```

**Key Responsibilities:**
- Version control prompt templates
- Maintain and expand taxonomy
- Store and retrieve entity patterns
- A/B test prompt variations

**Interfaces:**
- → Agent 3: Provides prompts and taxonomy
- ← Agent 9: Receives corrections to update patterns

---

### Agent 5: Validator

**Mission:** Ensure extracted data is correct and consistent.

**Validation Layers:**

```
Layer 1: DETERMINISTIC (Always run)
├── Balance sheet balances (A = L + E)
├── Cash flow reconciles (Begin + Net = End)
├── Derivation checks (GP = Rev - COGS)
├── Sign conventions (Revenue positive)
└── Format validation (numeric, dates)

Layer 2: GUIDED (Claude reasoning)
├── Explain why BS doesn't balance
├── Identify unusual but valid cases
├── Suggest potential fixes
└── Flag ambiguous items

Layer 3: STATISTICAL (Optional)
├── YoY change reasonableness
├── Margin within industry range
├── Outlier detection
└── Historical pattern comparison
```

**Output:**
```python
@dataclass
class ValidationResult:
    status: str  # 'passed', 'warnings', 'failed'
    deterministic_checks: List[CheckResult]
    claude_reasoning: str
    flags: List[ValidationFlag]
    suggested_fixes: List[Fix]
    final_confidence: Decimal
```

**Interfaces:**
- ← Agent 3: Receives extraction for validation
- → Agent 6: Emits validation events
- → Agent 7: Sends for calibration

---

### Agent 6: Lineage Tracker (EXISTENTIAL)

**Mission:** Ensure 100% lineage completeness. Every value traces to source.

**Event Schema:**
```python
@dataclass
class LineageEvent:
    id: UUID
    timestamp: datetime
    
    # Who
    actor_type: str  # 'system', 'claude', 'user'
    actor_id: str    # 'extraction_orchestrator', 'user:123'
    
    # What
    action: str      # 'parsed', 'triaged', 'mapped', 'validated', 'corrected'
    stage: str       # 'parsing', 'triage', 'structure', 'mapping', 'verification'
    
    # Target
    target_type: str  # 'cell', 'sheet', 'line_item', 'mapping'
    target_id: UUID
    
    # Data
    input_snapshot: Dict
    output_snapshot: Dict
    
    # Source tracing
    source_file_id: UUID
    source_sheet: str
    source_cell: str
    
    # Quality
    confidence: Decimal
    claude_reasoning: Optional[str]
```

**Provenance Query:**
```
GET /api/v1/lineage/{value_id}

Response:
{
  "value": 5200000,
  "canonical_name": "ebitda",
  "chain": [
    {"stage": "parsing", "action": "extracted", "source_cell": "B42"},
    {"stage": "mapping", "action": "mapped", "method": "guided_claude"},
    {"stage": "verification", "action": "validated", "checks_passed": 5}
  ]
}
```

**Interfaces:**
- ← All agents: Receive lineage events
- → Agent 8: Serve provenance queries
- → Agent 9: Provide audit data

---

### Agent 7: Confidence Calibrator

**Mission:** Ensure confidence scores match actual accuracy.

**Approach:**
```
1. Collect Claude's raw confidence scores
2. Collect human corrections (ground truth)
3. Apply Platt scaling to calibrate
4. Track Expected Calibration Error (ECE)
5. Adjust thresholds based on performance
```

**Thresholds:**
```python
class ConfidenceThresholds:
    auto_approve = 0.90    # High confidence, no review needed
    suggest_review = 0.70  # Medium confidence, optional review
    require_review = 0.50  # Low confidence, must review
```

**Metrics:**
- ECE (Expected Calibration Error): Target < 0.05
- Auto-approve accuracy: Target > 95%
- Review rate: Target < 15%

**Interfaces:**
- ← Agent 5: Receives validation results
- → Agent 3: Provides calibrated confidence
- → Agent 9: Provides calibration metrics

---

### Agent 8: Excel Add-in (EXISTENTIAL)

**Mission:** Build the Excel add-in analysts will love.

**User Journey:**
```
1. Open Excel → Click add-in icon
2. Task pane opens → Authenticated
3. Click "Extract Model" → Select current workbook
4. Progress: Parsing... Analyzing... Mapping... Validating...
5. Complete: "Extracted 127 values. 112 auto-approved, 15 need review."
6. Click "Import to Sheet" → Data appears in new worksheet
7. Click any cell → Provenance panel shows source
8. Type =GETMETRIC("revenue", "2024") → Value appears
9. Low-confidence cells highlighted yellow
10. Click "Review Queue" → Opens dashboard
```

**Components:**
```
Task Pane
├── Upload Section
│   ├── File selector / current workbook
│   └── Entity selector (dropdown)
├── Progress Display
│   ├── Stage indicator (5 stages)
│   ├── Progress bar
│   └── Cost estimate
├── Results Summary
│   ├── Values extracted
│   ├── Confidence breakdown
│   └── Review needed count
└── Provenance Panel
    ├── Source file/sheet/cell
    ├── Mapping method & reasoning
    ├── Validation checks
    └── Edit history
```

**Custom Functions:**
```
=GETMETRIC(entity, metric, period)   → Returns value
=CONFIDENCE(cell)                    → Returns confidence score
=SOURCE(cell)                        → Returns source description
```

**Interfaces:**
- ← Agent 2: API calls
- ← Agent 6: Provenance queries

---

### Agent 9: Review Dashboard

**Mission:** Enable fast review and corrections.

**Key Screens:**
```
1. Model List
   - All processed models
   - Status, confidence, review count
   - Filter and search

2. Review Queue
   - Items needing review (sorted by priority)
   - Show: original label, suggested mapping, confidence
   - Actions: approve, correct, skip

3. Correction Interface
   - Side-by-side: original vs. suggested
   - Taxonomy search/dropdown
   - "Apply to all similar" checkbox
   - <3 clicks to complete

4. System Health
   - Processing queue depth
   - Accuracy trends
   - Calibration metrics
   - Cost tracking
```

**Correction Flow:**
```
User corrects mapping
    ↓
Agent 9 saves correction
    ↓
Agent 6 emits lineage event
    ↓
Agent 4 updates entity patterns
    ↓
Future extractions learn from correction
```

**Interfaces:**
- ← Agent 2: API calls
- → Agent 4: Entity pattern updates
- → Agent 6: Correction lineage events

---

## Team Composition

| Role | Agents | FTE |
|------|--------|-----|
| **Backend Engineer #1** | 1, 2 | 1.0 |
| **Backend Engineer #2** | 3, 4, 5, 7 | 1.0 |
| **Full-stack Engineer** | 8, 9 | 1.0 |
| **Part-time / Shared** | 6 (Lineage) | 0.5 |
| **Total** | | **3.5** |

---

## Agent Dependencies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEPENDENCY FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────┐
                              │   Upload    │
                              └──────┬──────┘
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │ Agent 2: API           │
                        │ (receives file, queues)│
                        └────────────┬───────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Agent 3: EXTRACTION ORCHESTRATOR                          │
│                                                                              │
│   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐       │
│   │ Parse   │──▶│ Triage  │──▶│Structure│──▶│ Mapping │──▶│ Verify  │       │
│   │(Claude) │   │(Claude) │   │(Claude) │   │(Claude) │   │(+Determ)│       │
│   └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘       │
│        │             │             │             │              │            │
│        └─────────────┴─────────────┴─────────────┴──────────────┘            │
│                                    │                                          │
│                          Agent 4: GUIDELINES                                  │
│                          (prompts, taxonomy)                                  │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
          ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
          │ Agent 5     │   │ Agent 6     │   │ Agent 7     │
          │ Validator   │   │ Lineage     │   │ Calibrator  │
          └─────────────┘   └──────┬──────┘   └─────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
          ┌─────────────────────┐     ┌─────────────────────┐
          │ Agent 8: ADD-IN    │     │ Agent 9: DASHBOARD   │
          │ (EXISTENTIAL)       │     │                     │
          └─────────────────────┘     └─────────────────────┘
```

---

## Integration Checkpoints

| Week | Checkpoint | Agents | Test |
|------|------------|--------|------|
| 3 | Foundation complete | 1, 2 | Upload file, job created |
| 5 | Guided extraction E2E | 3, 4 | Parse + triage + structure on 3 models |
| 6 | Mapping + validation | 3, 4, 5 | Full extraction on 5 models |
| 7 | Lineage complete | 6 | Every value has provenance |
| 8 | Calibration working | 7 | Confidence matches accuracy |
| 10 | Add-in functional | 8 | Upload → extract → import works |
| 11 | Dashboard functional | 9 | Review queue → correct works |
| 12 | Full system | All | 10 models, complete user journey |

---

## Metrics by Agent

| Agent | Primary Metric | Target |
|-------|----------------|--------|
| 2 (API) | Uptime | 99.9% |
| 3 (Orchestrator) | Processing time | <10 min (subsequent models) |
| 4 (Guidelines) | Entity pattern hit rate | >50% after 5 models |
| 5 (Validator) | False positive rate | <10% |
| 6 (Lineage) | Completeness | **100%** |
| 7 (Calibrator) | ECE | <0.05 |
| 8 (Add-in) | Cross-platform | Windows + Mac + Web |
| 9 (Dashboard) | Correction clicks | <3 |

---

*Agent Organization v3.0 — Guided Hybrid Architecture — February 19, 2026*
