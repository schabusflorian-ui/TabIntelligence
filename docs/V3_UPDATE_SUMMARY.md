# V3 Documentation Update Summary

## The Guided Hybrid Architecture

**Core Insight:** We provide structure, rules, and domain expertise. Claude provides reading, understanding, and reasoning. Together = stronger than either alone.

---

## Evolution: v1 → v2 → v3

| Aspect | v1 (Original) | v2 (Technical Review) | v3 (Guided Hybrid) |
|--------|---------------|----------------------|-------------------|
| Architecture | 10 agents | 12 + 3 sub-agents | **9 agents** |
| Extraction | Custom-built | Custom-built | **Guided Claude** |
| Timeline | 18 weeks | 18 weeks | **10-12 weeks** |
| Team size | 5 engineers | 5 engineers | **3-4 engineers** |
| Cost per model | $0 (compute) | $0 (compute) | **~$0.50 (Claude API)** |
| Accuracy approach | Train on data | Train on data | **Guide with expertise** |

---

## What Is Guided Extraction?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GUIDED EXTRACTION PRINCIPLE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐               │
│   │   OUR BRAIN  │     │ CLAUDE EYES  │     │   OUTPUT     │               │
│   │              │     │              │     │              │               │
│   │ • Taxonomy   │────▶│ • Reads file │────▶│ • Structured │               │
│   │ • Rules      │     │ • Understands│     │ • Validated  │               │
│   │ • Guidelines │     │ • Reasons    │     │ • With       │               │
│   │ • Patterns   │     │ • Maps       │     │   Lineage    │               │
│   └──────────────┘     └──────────────┘     └──────────────┘               │
│                                                                              │
│   WE PROVIDE:           CLAUDE DOES:         WE ADD:                        │
│   Domain expertise      Understanding        Persistence                    │
│   Structure             Reasoning            Lineage                        │
│   Validation rules      Edge case handling   Entity learning                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The 5-Stage Guided Pipeline

| Stage | Our Guidelines | Claude Does | We Add |
|-------|----------------|-------------|--------|
| **1. Parsing** | Cell extraction format, formula rules | Reads Excel with context | Dependency graph, lineage |
| **2. Triage** | Tier definitions, skip criteria | Classifies sheets intelligently | Processing queue |
| **3. Structure** | Section taxonomy, period patterns | Identifies with understanding | Validation |
| **4. Mapping** | Canonical taxonomy, entity context | Maps with reasoning | Cache updates, lineage |
| **5. Verification** | Validation rules | Explains anomalies | Final confidence, review flags |

---

## New Agent Structure (9 Agents)

### Foundation Layer (Weeks 1-3)

| # | Agent | Responsibility | Change from v2 |
|---|-------|----------------|----------------|
| 1 | Database Architect | Schema, entity patterns, storage | Same |
| 2 | API & Infrastructure | Endpoints, auth, file handling | Same |

### Guided Extraction Engine (Weeks 4-8)

| # | Agent | Responsibility | Change from v2 |
|---|-------|----------------|----------------|
| 3 | **Extraction Orchestrator** | Multi-stage guided extraction, Claude calls | **NEW** - replaces Parser, Triage, Structure |
| 4 | **Guidelines Manager** | Prompts, taxonomy, entity patterns | **NEW** - replaces Mapper sub-agents |
| 5 | Validator | Deterministic + guided verification | Simplified from v2 |

### Trust Layer (Weeks 4-8)

| # | Agent | Responsibility | Change from v2 |
|---|-------|----------------|----------------|
| 6 | Lineage Tracker | Provenance, audit trail | Was Agent 9 |
| 7 | Confidence Calibrator | Score calibration, thresholds | Was Agent 10 |

### User Interface Layer (Weeks 9-12)

| # | Agent | Responsibility | Change from v2 |
|---|-------|----------------|----------------|
| 8 | Excel Add-in | Task pane, provenance panel | Was Agent 11 |
| 9 | Review Dashboard | Review queue, corrections | Was Agent 12 |

---

## What Was Removed (Claude Handles)

| v2 Component | v2 Agent | v3 Status |
|--------------|----------|-----------|
| Excel Parser | Agent 3 | **Claude with guided prompt** |
| Tab Triage | Agent 4 | **Claude with guided prompt** |
| Structure Recognition | Agent 5 | **Claude with guided prompt** |
| Mapping Planning | Agent 6a | **Claude with guided prompt** |
| Mapping Execution | Agent 6b | **Claude with guided prompt** |
| Mapping Verification | Agent 6c | **Merged into Validator** |

---

## What We Still Own (The Moat)

| Asset | Why It's Valuable | Agent Owner |
|-------|-------------------|-------------|
| **Canonical Taxonomy** | Claude uses it, we define standards | Agent 4 |
| **Entity Patterns** | Learning across extractions, improves over time | Agent 4 |
| **Lineage** | Full provenance, compliance, trust | Agent 6 |
| **Guided Prompts** | Our domain expertise encoded | Agent 4 |
| **Validation Rules** | Deterministic quality assurance | Agent 5 |
| **Warehouse** | Cross-model queries, portfolio analytics | Agent 1 |

---

## Timeline Comparison

| Milestone | v2 (Full Build) | v3 (Guided Hybrid) | Savings |
|-----------|-----------------|--------------------|---------| 
| Foundation complete | Week 3 | Week 3 | — |
| Extraction working | Week 11 | **Week 6** | **5 weeks** |
| Add-in functional | Week 14 | **Week 10** | **4 weeks** |
| Pilot ready | Week 18 | **Week 12** | **6 weeks** |

---

## Key Libraries & Research

### Core Dependencies

| Library | Purpose | Agent |
|---------|---------|-------|
| `openpyxl` | Excel read/write, formatting, formulas | Agent 3 |
| `formulas` | Parse Excel formulas to dependency graph | Agent 3 |
| `networkx` | Graph analysis for lineage/dependencies | Agent 3, 6 |
| `anthropic` | Claude API | Agent 3 |

### Research Applied: SpreadsheetLLM (Microsoft)

We apply compression concepts from Microsoft's SpreadsheetLLM research to reduce Claude tokens by 50-80%:

| Technique | What It Does | Token Reduction |
|-----------|--------------|-----------------|
| Structural Anchor Extraction | Identify headers, skip repetitive structure | ~30% |
| Inverted-Index Translation | Don't repeat similar values | ~25% |
| Data-Format-Aware Aggregation | Group similar cells | ~20% |

### Open Source References

| Project | Use For | Link |
|---------|---------|------|
| LLMExcel | Add-in architecture patterns | github.com/liminityab/LLMExcel |
| spreadsheet-llm-unofficial | Compression techniques | github.com/dtung8068/spreadsheet-llm-unofficial |

---

## Cost Model

| Item | v2 (Full Build) | v3 (Guided Hybrid) | v3 + Compression |
|------|-----------------|-------------------|------------------|
| Engineering (18 wks × 5 eng) | ~$500K | — | — |
| Engineering (12 wks × 4 eng) | — | ~$280K | ~$280K |
| Claude API (1000 models/mo) | $0 | ~$500/month | **~$150/month** |
| **Total Year 1** | **~$500K** | **~$286K** | **~$282K** |

*Compression techniques reduce token usage by 50-70%, cutting API costs significantly.*

---

## Accuracy Expectations

| Approach | Expected Accuracy | Why |
|----------|-------------------|-----|
| Naive Claude | 70-80% | No domain guidance |
| Full Custom Build | 90%+ (eventually) | Needs lots of training data |
| **Guided Hybrid** | **85-95%** | Claude understanding + our expertise |

---

## Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Build vs. Buy extraction | **Guided hybrid** | Faster, cheaper, comparable accuracy |
| Agent count | **9 agents** (down from 15) | Claude replaces parsing/mapping |
| Development time | **10-12 weeks** | Reduced scope |
| Team size | **3-4 engineers** | Less custom code |
| Model agnostic | **Yes, by design** | Taxonomy is pluggable |
| Future model creation | **Enabled** | Same infrastructure works |

---

## Document Inventory (v3)

| Document | Location | Content |
|----------|----------|---------|
| V3 Update Summary | `/v3/V3_UPDATE_SUMMARY.md` | This document |
| Agent Organization | `/v3/agent_organization_v3.md` | 9-agent structure |
| Agent Kickoff Briefs | `/v3/agent_kickoff_briefs_v3.md` | All 9 agents in one doc |
| Product Integration Plan | `/v3/product_integration_plan_v3.md` | Architecture, pipeline, timeline |
| Project Governance | `/v3/project_governance_v3.md` | Quality gates, tracking |
| Agent Diagram | `/v3/agent_organization_v3.mermaid` | Visual diagram |

---

## Migration from v2

If you have v2 documents, here's what changed:

| v2 Document Section | v3 Change |
|---------------------|-----------|
| Agent 3 (Parser) | Removed → Agent 3 (Extraction Orchestrator) |
| Agent 4 (Triage) | Removed → Handled by Agent 3 |
| Agent 5 (Structure) | Removed → Handled by Agent 3 |
| Agent 6 (Mapper + sub-agents) | Removed → Agent 4 (Guidelines Manager) |
| Agent 7 (Validator) | Simplified → Agent 5 |
| Agent 8 (Pipeline) | Merged into Agent 3 |
| Agent 9 (Lineage) | Renumbered → Agent 6 |
| Agent 10 (Calibrator) | Renumbered → Agent 7 |
| Agent 11 (Add-in) | Renumbered → Agent 8 |
| Agent 12 (Dashboard) | Renumbered → Agent 9 |

---

## What Stays the Same from v2

| Concept | Status |
|---------|--------|
| The Four Laws | ✅ Unchanged |
| Existential Challenges (Lineage 100%, Add-in adoption) | ✅ Unchanged |
| Tier-based accuracy expectations | ✅ Unchanged |
| MVP scope (P&L, BS, CF only) | ✅ Unchanged |
| Canonical taxonomy (~100 items) | ✅ Unchanged |
| Entity learning / patterns | ✅ Unchanged |
| Lineage as the moat | ✅ Unchanged |

---

## Prototype Validation (Completed)

We validated the hybrid approach with a working prototype:

```
✅ openpyxl extracts all needed data:
   • Cell values (94 cells)
   • Formulas (20 formulas) 
   • Bold formatting (headers/totals)
   • Indentation (hierarchy)

✅ Claude understands pre-parsed data:
   • Sheet classification: 100% accurate
   • Line item mapping: 32/34 items mapped
   • Hierarchy detection: Working
```

**Recommendation:** Core dependencies validated. Proceed with full implementation.

---

*V3 Update — Guided Hybrid Architecture — February 19, 2026*
