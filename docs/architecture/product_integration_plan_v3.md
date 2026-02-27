# Excel Model Intelligence Platform
## Product Integration Plan v3.0

**Document Owner:** Product Manager
**Scope:** Excel Model Workflow — Guided Hybrid Architecture
**Resources:** 9 Agents, 3-4 Engineers, 10-12 Weeks
**Last Updated:** February 19, 2026

---

# What Changed from v2.0

| Aspect | v2.0 | v3.0 | Rationale |
|--------|------|------|-----------|
| **Agent count** | 12 + 3 sub-agents | **9 agents** | Claude handles parsing/mapping |
| **Extraction approach** | Custom-built pipeline | **Guided Claude** | Faster, comparable accuracy |
| **Timeline** | 18 weeks | **10-12 weeks** | Reduced custom code |
| **Team size** | 5 engineers | **3-4 engineers** | Less to build |
| **Cost model** | $0 per model | **~$0.50 per model** | Claude API costs |
| **Core differentiator** | Custom extraction | **Domain expertise + lineage** | We guide, Claude extracts |

---

# Part 1: Strategic Foundation

## 1.1 Product Vision

**One-liner:** Turn any Excel financial model into structured, queryable, auditable data—without losing context.

**The Guided Hybrid Approach:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   WE PROVIDE:              CLAUDE DOES:            WE ADD:                  │
│   ─────────────            ────────────            ────────                 │
│   • Canonical taxonomy     • Reads Excel           • Lineage (the moat)    │
│   • Tier definitions       • Understands context   • Entity patterns       │
│   • Entity context         • Maps with reasoning   • Validation            │
│   • Validation rules       • Explains edge cases   • Persistence           │
│                                                                              │
│   DOMAIN EXPERTISE    +    AI UNDERSTANDING    =   STRUCTURED OUTPUT       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 1.2 Scope Definition

### MVP Scope (V1) — Unchanged from v2
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MVP: CORE STATEMENTS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  EXTRACT            │  SKIP                │  QUALITY                      │
│  • Income Statement │  • Revenue builds    │  • >85% accuracy (Tier 1)     │
│  • Balance Sheet    │  • Assumptions       │  • <20% human review          │
│  • Cash Flow        │  • Scratch tabs      │  • 100% lineage               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What We Own (The Moat)

| Asset | Why It's Valuable | Defensibility |
|-------|-------------------|---------------|
| **Canonical Taxonomy** | Industry standard for financial terms | Network effects |
| **Entity Patterns** | Improves with every extraction | Compounding data |
| **Lineage** | Full audit trail, compliance-ready | No one else has this |
| **Guided Prompts** | Domain expertise encoded | Hard to replicate |
| **Warehouse** | Cross-model queries | Portfolio analytics |

### Future Enablements

This architecture enables:
- **Model creation** (V2): Same taxonomy, reverse direction
- **Model agnostic** (V2+): Pluggable taxonomies for real estate, etc.
- **Portfolio analytics** (V2+): Cross-model queries
- **Benchmarking** (V3): Industry comparisons

## 1.3 Success Metrics

### Primary Metrics

| Metric | Target | Red Line | Measurement |
|--------|--------|----------|-------------|
| Extraction accuracy (Tier 1) | >85% | <75% | Ground truth comparison |
| Lineage completeness | 100% | <100% | Automated validator |
| Human review rate | <20% | >30% | Confidence threshold |
| Time to extract (first model) | <15 min | >30 min | End-to-end timing |
| Time to extract (subsequent) | <8 min | >15 min | Entity cache effect |
| Cost per model | <$0.75 | >$1.50 | Claude API tracking |

### Quality Metrics

| Metric | Target | Red Line |
|--------|--------|----------|
| Calibration error (ECE) | <0.05 | >0.10 |
| Auto-approve accuracy | >92% | <85% |
| Provenance query latency | <500ms | >2s |

---

# Part 2: System Architecture

## 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GUIDED HYBRID ARCHITECTURE                                │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   EXCEL ADD-IN  │  ← Agent 8 (EXISTENTIAL)
                              │   (User Gateway)│
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │   API GATEWAY   │  ← Agent 2
                              │   (FastAPI)     │
                              └────────┬────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌───────────────┐     ┌────────────────────────────────┐     ┌───────────────┐
│   INGESTION   │     │   GUIDED EXTRACTION ENGINE     │     │    QUERY      │
│   Agent 2     │     │                                │     │   SERVICE     │
│               │     │   ┌──────────────────────┐     │     │   Agent 2     │
│ • File upload │     │   │ Agent 3: Orchestrator│     │     │               │
│ • Job queue   │     │   │ (Calls Claude)       │     │     │ • Metrics     │
│ • Storage     │     │   └──────────┬───────────┘     │     │ • Lineage     │
└───────────────┘     │              │                 │     └───────────────┘
                      │   ┌──────────▼───────────┐     │
                      │   │ Agent 4: Guidelines  │     │
                      │   │ (Prompts, Taxonomy)  │     │
                      │   └──────────┬───────────┘     │
                      │              │                 │
                      │   ┌──────────▼───────────┐     │
                      │   │ Agent 5: Validator   │     │
                      │   │ (Deterministic+Claude│     │
                      │   └──────────────────────┘     │
                      └────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
          ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
          │ Agent 6         │ │ Agent 7         │ │ DATA LAYER      │
          │ Lineage         │ │ Calibrator      │ │ Agent 1         │
          │ (EXISTENTIAL)   │ │                 │ │ (PostgreSQL)    │
          └─────────────────┘ └─────────────────┘ └─────────────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
         ▼                     ▼
┌─────────────────┐   ┌─────────────────┐
│ Agent 8: ADD-IN │   │ Agent 9: DASH   │
│ (EXISTENTIAL)   │   │                 │
└─────────────────┘   └─────────────────┘
```

## 2.1.1 Technical Stack & Libraries

### Core Dependencies

| Category | Library | Version | Purpose |
|----------|---------|---------|---------|
| **Excel Parsing** | `openpyxl` | ≥3.1.0 | Read/write Excel with full formatting |
| **Formula Analysis** | `formulas` | ≥1.2.0 | Parse formulas to AST, extract references |
| **Graph Analysis** | `networkx` | ≥3.0 | Dependency graph, lineage queries |
| **LLM** | `anthropic` | ≥0.18.0 | Claude API |
| **API** | `fastapi` | ≥0.109.0 | REST API framework |
| **Database** | `sqlalchemy` | ≥2.0.0 | ORM |
| **Add-in** | `Office.js` | latest | Excel integration |

### Research Applied

**SpreadsheetLLM (Microsoft Research, July 2024):**
We apply key compression concepts to reduce token usage by 50-70%:

| Technique | Implementation | Token Savings |
|-----------|----------------|---------------|
| Structural Anchor Extraction | Send headers only, not all cells | ~30% |
| Inverted-Index Translation | Deduplicate repeated values | ~25% |
| Data-Format-Aware Aggregation | Group similar cells | ~15% |

### Open Source References

| Project | What We Use | Link |
|---------|-------------|------|
| **LLMExcel** | Add-in architecture patterns | github.com/liminityab/LLMExcel |
| **spreadsheet-llm-unofficial** | Compression implementation | github.com/dtung8068/spreadsheet-llm-unofficial |

### Build vs Buy Validation

| Capability | How We Do It | Complexity |
|------------|--------------|------------|
| Read Excel files | `openpyxl` | ✅ Easy |
| Parse formulas | `formulas` library | ✅ Easy |
| Dependency graph | `networkx` | ✅ Easy |
| Understand structure | Claude + prompts | ✅ Medium |
| Excel add-in | Office.js | ⚠️ Medium-Hard |
| Cross-model queries | PostgreSQL + API | ✅ Medium |

## 2.2 The 5-Stage Guided Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      5-STAGE GUIDED EXTRACTION                               │
└─────────────────────────────────────────────────────────────────────────────┘

STAGE 1: GUIDED PARSING                                        Time: ~30-60s
┌─────────────────────────────────────────────────────────────────────────────┐
│  Our Guidelines:          Claude Does:              We Add:                 │
│  • Cell extraction format • Reads Excel with        • Dependency graph      │
│  • Formula capture rules    full understanding      • Circular detection    │
│  • Formatting to capture  • Identifies cell types   • Lineage events        │
│                           • Understands context                             │
│                                                                             │
│  Output: ParsedModel with sheets, cells, formulas, formatting               │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
STAGE 2: GUIDED TRIAGE                                         Time: ~10-20s
┌─────────────────────────────────────────────────────────────────────────────┐
│  Our Guidelines:          Claude Does:              We Add:                 │
│  • Tier 1-4 definitions   • Classifies each sheet  • Processing queue      │
│  • Skip criteria          • Understands intent     • Lineage events        │
│  • Layout patterns        • Handles edge names                              │
│                                                                             │
│  Tiers:                                                                     │
│  • Tier 1: P&L, BS, CF (PROCESS_HIGH, target 90%)                          │
│  • Tier 2: Debt, D&A (PROCESS_MEDIUM, target 80%)                          │
│  • Tier 3: Assumptions (PROCESS_LOW, target 70%)                           │
│  • Tier 4: Scratch (SKIP)                                                  │
│                                                                             │
│  Output: TriageResult per sheet (tier, decision, confidence)               │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
STAGE 3: GUIDED STRUCTURE                                      Time: ~60-90s
┌─────────────────────────────────────────────────────────────────────────────┐
│  Our Guidelines:          Claude Does:              We Add:                 │
│  • Section definitions    • Identifies sections    • Validation            │
│  • Period patterns        • Parses time periods    • Lineage events        │
│  • Hierarchy rules        • Detects hierarchy                              │
│                           • Marks hist vs. proj                            │
│                                                                             │
│  Output: ModelStructure (sections, periods, line_items with hierarchy)     │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
STAGE 4: GUIDED MAPPING                                        Time: ~90-180s
┌─────────────────────────────────────────────────────────────────────────────┐
│  Our Guidelines:          Claude Does:              We Add:                 │
│  • Canonical taxonomy     • Maps with reasoning    • Entity pattern cache  │
│  • Entity context         • Handles edge cases     • Pattern updates       │
│  • Previous patterns      • Provides alternatives  • Lineage events        │
│                           • Explains decisions                             │
│                                                                             │
│  Output: MappingResult per item (canonical_name, confidence, reasoning)    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
STAGE 5: VERIFICATION                                          Time: ~30-60s
┌─────────────────────────────────────────────────────────────────────────────┐
│  Deterministic:           Claude Does:              We Add:                 │
│  • BS balance check       • Explains anomalies     • Final confidence      │
│  • Derivation checks      • Reasons about edge     • Review flags          │
│  • Sign conventions       • Suggests fixes         • Lineage events        │
│                                                                             │
│  Output: VerifiedExtraction (validated values, flags, confidence)          │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME:
• First model from entity: 8-15 minutes
• Subsequent models (cached patterns): 5-10 minutes
```

## 2.3 Cost Model

| Stage | Est. Input Tokens | Est. Output Tokens | Est. Cost |
|-------|-------------------|--------------------|-----------| 
| Parsing | ~50,000 | ~20,000 | $0.17 |
| Triage | ~5,000 | ~2,000 | $0.02 |
| Structure | ~20,000 | ~10,000 | $0.09 |
| Mapping | ~30,000 | ~15,000 | $0.14 |
| Verification | ~15,000 | ~5,000 | $0.05 |
| **Total** | ~120,000 | ~52,000 | **~$0.47** |

**At 1000 models/month: ~$470/month in Claude costs**

---

# Part 3: Agent Organization

## 3.1 The 9 Agents

### Foundation Layer (Weeks 1-3)

| # | Agent | Responsibility | Owner |
|---|-------|----------------|-------|
| 1 | Database Architect | Schema, entity patterns, taxonomy | Backend #1 |
| 2 | API & Infrastructure | FastAPI, S3, auth, job queue | Backend #1 |

### Guided Extraction Engine (Weeks 4-8)

| # | Agent | Responsibility | Owner |
|---|-------|----------------|-------|
| 3 | Extraction Orchestrator | 5-stage pipeline, Claude calls | Backend #2 |
| 4 | Guidelines Manager | Prompts, taxonomy, patterns | Backend #2 |
| 5 | Validator | Deterministic + guided checks | Backend #2 |
| 6 | Lineage Tracker | Provenance, audit (EXISTENTIAL) | Shared |
| 7 | Confidence Calibrator | ECE, thresholds | Backend #2 |

### User Interface Layer (Weeks 9-12)

| # | Agent | Responsibility | Owner |
|---|-------|----------------|-------|
| 8 | Excel Add-in | Task pane, provenance (EXISTENTIAL) | Full-stack |
| 9 | Review Dashboard | Queue, corrections | Full-stack |

## 3.2 Team Composition

| Role | Agents | FTE | Weeks |
|------|--------|-----|-------|
| Backend Engineer #1 | 1, 2 | 1.0 | 1-12 |
| Backend Engineer #2 | 3, 4, 5, 7 | 1.0 | 4-12 |
| Full-stack Engineer | 8, 9 | 1.0 | 9-12 |
| Shared (Lineage) | 6 | 0.5 | 4-12 |
| **Total** | | **3.5** | **12 weeks** |

---

# Part 4: Interface Contracts

## 4.1 Agent 3 → Agent 4 (Orchestrator → Guidelines)

```python
# Orchestrator requests prompts and context from Guidelines

class GuidelinesRequest:
    stage: str                  # 'parsing', 'triage', 'structure', 'mapping'
    entity_id: Optional[UUID]   # For entity-specific context
    sheet_type: Optional[str]   # For structure stage

class GuidelinesResponse:
    prompt_template: str
    taxonomy: Optional[List[TaxonomyItem]]
    entity_patterns: Optional[List[EntityPattern]]
    tier_definitions: Optional[Dict]
```

## 4.2 Agent 3 → Agent 5 (Orchestrator → Validator)

```python
# Orchestrator sends extraction for validation

class ValidationRequest:
    file_id: UUID
    extraction: ExtractionResult
    mappings: List[MappingResult]

class ValidationResponse:
    status: str  # 'passed', 'warnings', 'failed'
    deterministic_results: List[CheckResult]
    claude_reasoning: str
    flags: List[ValidationFlag]
    composite_confidence: Dict[UUID, float]
```

## 4.3 Agent 6 Interface (Lineage)

```python
# All agents emit lineage events

class LineageEvent:
    action: str
    stage: str
    target_type: str
    target_id: UUID
    input_snapshot: Dict
    output_snapshot: Dict
    source_file_id: UUID
    source_sheet: Optional[str]
    source_cell: Optional[str]
    confidence: Optional[float]
    claude_reasoning: Optional[str]

# Query interface
class ProvenanceQuery:
    value_id: UUID

class ProvenanceResponse:
    value_id: UUID
    chain: List[LineageStep]
    source_summary: str
```

## 4.4 Agent 8 → Agent 2 (Add-in → API)

```python
# Add-in API contracts

# Upload
POST /api/v1/files/upload
Request: { file: bytes, entity_id: UUID }
Response: { file_id: UUID, job_id: UUID }

# Progress (SSE)
GET /api/v1/jobs/{job_id}/stream
Events: { stage: str, progress: int, message: str }

# Results
GET /api/v1/extractions/{file_id}
Response: { values: List[Value], summary: Summary }

# Provenance
GET /api/v1/lineage/{value_id}
Response: { chain: List[Step], source_summary: str }

# Metrics
GET /api/v1/entities/{id}/metrics/{name}?period={period}
Response: { value: float, confidence: float }
```

---

# Part 5: Timeline

## 5.1 Phase Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: FOUNDATION                                         Weeks 1-3      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Agents: 1, 2                                                               │
│ Deliverables:                                                              │
│   • Database schema (entities, patterns, lineage, taxonomy)                │
│   • API scaffold with auth and file upload                                 │
│   • Job queue and S3 storage                                               │
│   • Canonical taxonomy seeded (100+ items)                                 │
│                                                                             │
│ Milestone: Upload file → job created → status queryable                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: GUIDED EXTRACTION                                  Weeks 4-8      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Agents: 3, 4, 5, 6, 7                                                      │
│ Deliverables:                                                              │
│   • 5-stage guided pipeline (parsing → verification)                       │
│   • Prompt templates and versioning                                        │
│   • Entity pattern system                                                  │
│   • Deterministic validation rules                                         │
│   • Lineage emission and queries                                           │
│   • Confidence calibration                                                 │
│                                                                             │
│ Milestones:                                                                │
│   • Week 5: Parse + triage working on 3 test models                        │
│   • Week 6: Full pipeline E2E                                              │
│   • Week 7: Lineage 100% complete                                          │
│   • Week 8: Calibration working, accuracy >80%                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: USER INTERFACE                                     Weeks 9-12     │
├─────────────────────────────────────────────────────────────────────────────┤
│ Agents: 8, 9                                                               │
│ Deliverables:                                                              │
│   • Excel add-in (upload, progress, results, provenance)                   │
│   • Custom functions (GETMETRIC, CONFIDENCE, SOURCE)                       │
│   • Review dashboard (queue, corrections)                                  │
│   • System health dashboard                                                │
│                                                                             │
│ Milestones:                                                                │
│   • Week 10: Add-in upload → extract → import working                      │
│   • Week 11: Provenance panel functional                                   │
│   • Week 12: Full user journey, 10 models tested                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 5.2 Weekly Milestones

| Week | Primary Focus | Key Deliverable | Gate |
|------|---------------|-----------------|------|
| 1 | DB schema | Core tables, taxonomy | — |
| 2 | API + Auth | Upload working | — |
| 3 | Job queue + Lineage schema | Jobs tracked | **G1: Foundation** |
| 4 | Guided parsing | Parse works on 3 models | — |
| 5 | Guided triage + structure | Triage + structure working | — |
| 6 | Guided mapping | Full pipeline E2E | **G2: Pipeline** |
| 7 | Validation + Lineage | 100% lineage | — |
| 8 | Calibration + Polish | Accuracy >80%, ECE <0.08 | **G3: Accuracy** |
| 9 | Add-in scaffold | Loads in Excel | — |
| 10 | Add-in upload + results | Upload → extract works | — |
| 11 | Provenance panel | Click → source works | **G4: Add-in** |
| 12 | Dashboard + Final | 10 models, full journey | **G5: Launch** |

---

# Part 6: Risk Management

## 6.1 Existential Challenges

| Challenge | Agent | Target | Mitigation |
|-----------|-------|--------|------------|
| **Lineage 100%** | 6 | Complete provenance | PR blocking, automated validation |
| **Add-in Works** | 8 | Cross-platform | Weekly testing on all platforms |

**Note:** Mapping accuracy is lower risk in v3 because Claude handles it. We validate output rather than building the engine.

## 6.2 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Claude API unreliable | Low | High | Retry logic, circuit breaker |
| Claude output inconsistent | Medium | Medium | Structured prompts, validation |
| Cost overrun | Low | Medium | Token tracking, caching |
| Lineage incomplete | Medium | Critical | PR blocking, auto-validation |

## 6.3 Quality Gates

| Gate | Week | Criteria | Failure Action |
|------|------|----------|----------------|
| G1: Foundation | 3 | DB + API working, taxonomy seeded | Extend Phase 1 |
| G2: Pipeline | 6 | Full E2E on 5 models | Debug pipeline |
| G3: Accuracy | 8 | >80% accuracy, lineage 100% | Tune prompts |
| G4: Add-in | 11 | Works on Windows + Mac | Debug platform issues |
| G5: Launch | 12 | 10 models, full journey | Extend hardening |

---

# Part 7: What We Learned and Applied

## From v2 Technical Review

| Learning | v2 Approach | v3 Approach |
|----------|-------------|-------------|
| Mapping is hard | Build 3 sub-agents | **Let Claude do it with our guidance** |
| Need lots of training data | Collect 50+ models | **Claude already trained, we guide** |
| Lineage is existential | Same | Same (unchanged) |

## From Competitive Analysis

| Learning | Source | How Applied |
|----------|--------|-------------|
| Multi-agent verification | Shortcut | **Claude reasons at each stage** |
| "Instantly auditable" | Shortcut | **Provenance panel** |
| Taxonomy is the moat | Fundamental | **We own the taxonomy** |

## From "Why Not Just Use Claude" Analysis

| Question | Answer |
|----------|--------|
| Why not Claude in Excel alone? | No persistence, no lineage, no cross-model |
| Why not Shortcut? | They build models, we extract from models |
| What's our moat? | Taxonomy + entity patterns + lineage + warehouse |
| What does Claude do? | Reading + understanding + reasoning |
| What do we do? | Structure + persistence + learning + trust |

---

# Part 8: Success Definition

## MVP Definition of Done

```
FUNCTIONAL:
✓ Upload Excel model via add-in
✓ Process via 5-stage guided pipeline
✓ View extraction results in add-in
✓ View provenance for any cell
✓ Review and correct in dashboard
✓ Access data via =GETMETRIC() function

QUALITY:
✓ >85% accuracy on P&L, BS, CF (Tier 1)
✓ <20% human review rate
✓ 100% lineage completeness
✓ Calibration error <0.08

PERFORMANCE:
✓ First model: <15 minutes
✓ Subsequent models: <8 minutes
✓ Provenance query: <500ms
✓ Add-in load: <3 seconds
✓ Cost per model: <$0.75

USER EXPERIENCE:
✓ First-time user can upload in <2 minutes
✓ Review correction: <3 clicks
✓ Works on Windows, Mac, Excel Online
```

## What Success Looks Like (Week 12)

> Sarah opens a deal model in Excel. She clicks our add-in and selects "Extract Model." She watches the progress: "Parsing... Analyzing... Mapping... Validating..."

> In 7 minutes, it's done: "Extracted 142 values from P&L, Balance Sheet, Cash Flow. 124 auto-approved (87%), 18 need review."

> She clicks a few values to check. The provenance panel shows exactly where each came from, with Claude's reasoning: "Mapped 'Turnover' to 'revenue' — common UK/EU term for revenue."

> She opens the review queue, quickly approves 15 obvious ones, corrects 3 ThermoStore-specific terms. The system learns these for next time.

> Back in Excel, she types `=GETMETRIC("thermostore", "ebitda", "FY2024")` and the value appears. Her VP asks "where did that come from?" — she clicks the cell, shows the provenance panel. Full chain of custody, from source cell to normalized value.

> Next quarter, ThermoStore's updated model takes only 5 minutes. The system remembered their naming conventions.

---

*Product Integration Plan v3.0 — Guided Hybrid Architecture — February 19, 2026*
