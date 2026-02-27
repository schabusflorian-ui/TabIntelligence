# Agent Kickoff Briefs v3.0

## Guided Hybrid Architecture — All 9 Agents

---

# Executive Summary

## The Guided Hybrid Approach

We provide structure, rules, and domain expertise. Claude provides reading, understanding, and reasoning. Together = stronger than either alone.

**What Claude Does:**
- Reads Excel files with understanding
- Identifies structure and patterns
- Maps labels to our taxonomy with reasoning
- Explains edge cases and anomalies

**What We Own:**
- Canonical taxonomy (the standard)
- Entity patterns (learning over time)
- Lineage (full audit trail)
- Validation rules (deterministic checks)
- Warehouse (cross-model queries)

## The Rules of Engagement

1. **Your agent owns your domain** — You have authority over implementation within your scope
2. **Interfaces are contracts** — Once agreed, changes require PM approval
3. **Lineage is existential** — Every data transformation must emit lineage events
4. **Quality over speed** — Ship when quality gates pass

## Timeline Overview

```
Weeks 1-3:   Foundation (DB, API)
Weeks 4-8:   Guided Extraction (Orchestrator, Guidelines, Validation, Lineage, Calibration)
Weeks 9-12:  User Interface (Add-in, Dashboard) + Hardening
```

## Team Composition

| Role | Agents | Notes |
|------|--------|-------|
| Backend #1 | 1, 2 | Foundation + infrastructure |
| Backend #2 | 3, 4, 5, 7 | Extraction engine + validation |
| Full-stack | 8, 9 | Add-in + dashboard |
| Shared | 6 | Lineage (all agents emit events) |

## Core Libraries

| Library | Version | Agent(s) | Purpose |
|---------|---------|----------|---------|
| `openpyxl` | ≥3.1.0 | 3 | Excel read/write with full formatting |
| `formulas` | ≥1.2.0 | 3 | Parse Excel formulas to AST |
| `networkx` | ≥3.0 | 3, 6 | Dependency graph, lineage queries |
| `anthropic` | ≥0.18.0 | 3 | Claude API |
| `Office.js` | latest | 8 | Excel add-in |

### Research Applied

**SpreadsheetLLM (Microsoft Research, July 2024):**
- SheetCompressor: Reduces tokens by up to 96%
- Structural Anchor Extraction: Identifies header rows/columns
- We apply these concepts in Agent 4's prompt design

### Open Source References

| Project | Use For | Link |
|---------|---------|------|
| LLMExcel | Add-in patterns | github.com/liminityab/LLMExcel |
| spreadsheet-llm-unofficial | Compression techniques | github.com/dtung8068/spreadsheet-llm-unofficial |

---

# Agent 1: Database Architect

## Your Mission

Design and implement the data foundation. You're building the bedrock everything else sits on.

## Why This Matters

> "Entity patterns are how we learn. The taxonomy is how we standardize. The lineage is how we trust." — PM

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D1.1 | Core tables (entities, files, jobs) | Week 1 | P0 |
| D1.2 | Extraction tables (sheets, line_items, values) | Week 2 | P0 |
| D1.3 | Lineage tables (events, provenance) | Week 2 | P0 |
| D1.4 | Entity pattern tables | Week 2 | P0 |
| D1.5 | Taxonomy tables | Week 2 | P0 |
| D1.6 | Migration system (Alembic) | Week 3 | P0 |
| D1.7 | Seed data (canonical taxonomy) | Week 3 | P0 |
| D1.8 | Query optimization | Week 3 | P1 |

## Key Tables

```sql
-- Entities (companies/assets)
CREATE TABLE entities (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Entity patterns (learned mappings)
CREATE TABLE entity_patterns (
    id UUID PRIMARY KEY,
    entity_id UUID REFERENCES entities(id),
    original_label VARCHAR(500) NOT NULL,
    canonical_name VARCHAR(100) NOT NULL,
    confidence DECIMAL(5,4),
    occurrence_count INT DEFAULT 1,
    last_seen TIMESTAMPTZ,
    created_by VARCHAR(50)  -- 'claude', 'user_correction'
);

-- Lineage events (full audit trail)
CREATE TABLE lineage_events (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    actor_type VARCHAR(20) NOT NULL,  -- 'system', 'claude', 'user'
    actor_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    stage VARCHAR(50) NOT NULL,       -- 'parsing', 'mapping', etc.
    target_type VARCHAR(50) NOT NULL,
    target_id UUID NOT NULL,
    input_snapshot JSONB,
    output_snapshot JSONB,
    source_file_id UUID,
    source_sheet VARCHAR(255),
    source_cell VARCHAR(20),
    confidence DECIMAL(5,4),
    claude_reasoning TEXT
);

-- Canonical taxonomy
CREATE TABLE taxonomy (
    id UUID PRIMARY KEY,
    canonical_name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50) NOT NULL,    -- 'income_statement', 'balance_sheet', etc.
    display_name VARCHAR(255),
    aliases TEXT[],                   -- Common alternate names
    definition TEXT,
    typical_sign VARCHAR(10),         -- 'positive', 'negative'
    parent_canonical VARCHAR(100)     -- Hierarchy
);
```

## Success Criteria

- [ ] Schema supports all MVP use cases
- [ ] Entity pattern lookup < 50ms
- [ ] Lineage query < 500ms
- [ ] Taxonomy seeded with 100+ items

## Interfaces

```
→ Agent 3: Extraction storage, pattern lookup
→ Agent 4: Taxonomy and pattern CRUD
→ Agent 6: Lineage event storage and queries
```

---

# Agent 2: API & Infrastructure

## Your Mission

Build the API layer and infrastructure that makes everything work reliably.

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D2.1 | FastAPI scaffold | Week 1 | P0 |
| D2.2 | Docker configuration | Week 1 | P0 |
| D2.3 | S3 integration | Week 1 | P0 |
| D2.4 | File upload endpoint | Week 2 | P0 |
| D2.5 | Job queue (Celery + Redis) | Week 2 | P0 |
| D2.6 | Authentication (JWT) | Week 2 | P0 |
| D2.7 | SSE for progress streaming | Week 3 | P0 |
| D2.8 | Lineage query endpoints | Week 3 | P0 |
| D2.9 | OpenAPI documentation | Week 3 | P1 |
| D2.10 | Security baseline | Week 3 | P1 |

## API Endpoints

```python
# File Management
POST   /api/v1/files/upload           # Upload Excel file
GET    /api/v1/files/{file_id}        # File metadata
DELETE /api/v1/files/{file_id}        # Delete file

# Job Management
GET    /api/v1/jobs/{job_id}          # Job status
GET    /api/v1/jobs/{job_id}/stream   # SSE progress stream

# Extraction Results
GET    /api/v1/extractions/{file_id}           # Full extraction
GET    /api/v1/extractions/{file_id}/summary   # Summary only

# Lineage
GET    /api/v1/lineage/{value_id}              # Provenance chain
GET    /api/v1/lineage/{value_id}/full         # Complete history

# Entity Metrics
GET    /api/v1/entities/{id}/metrics           # All metrics
GET    /api/v1/entities/{id}/metrics/{name}    # Specific metric

# Review & Corrections
GET    /api/v1/review/queue                    # Items needing review
POST   /api/v1/mappings/{id}/correct           # Submit correction
POST   /api/v1/mappings/{id}/approve           # Approve mapping

# System
GET    /api/v1/health                          # Health check
GET    /api/v1/metrics                         # System metrics
```

## Success Criteria

- [ ] API handles 50 concurrent uploads
- [ ] 99.9% uptime for core endpoints
- [ ] SSE delivers progress updates in real-time
- [ ] Lineage query < 500ms

---

# Agent 3: Extraction Orchestrator

## Your Mission

Coordinate multi-stage guided extraction using Claude. You're the conductor of the extraction pipeline.

## Why This Matters

> "The pipeline IS the product. Each stage must be reliable, traceable, and recoverable."

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D3.1 | Claude API integration | Week 4 | P0 |
| D3.2 | Stage 1: Guided Parsing | Week 4 | P0 |
| D3.3 | Stage 2: Guided Triage | Week 5 | P0 |
| D3.4 | Stage 3: Guided Structure | Week 5 | P0 |
| D3.5 | Stage 4: Guided Mapping | Week 6 | P0 |
| D3.6 | Stage 5: Verification integration | Week 6 | P0 |
| D3.7 | Error handling & retries | Week 7 | P0 |
| D3.8 | Progress streaming (SSE) | Week 7 | P0 |
| D3.9 | Cost tracking | Week 7 | P1 |
| D3.10 | Performance optimization | Week 8 | P1 |

## Core Libraries

```python
# Required imports for Agent 3
import openpyxl                      # Excel parsing
from formulas import Parser          # Formula AST parsing
import networkx as nx                # Dependency graph
from anthropic import Anthropic      # Claude API
```

### Formula Parsing with `formulas`

```python
from formulas import Parser

def parse_formula_references(formula: str) -> list:
    """Extract cell references from Excel formula."""
    parser = Parser()
    try:
        ast = parser.parse(formula)
        return list(ast.get_references())
    except:
        return []

# Example
refs = parse_formula_references("=SUM(A1:A10) + B5 * 1.1")
# Returns: ['A1:A10', 'B5']
```

### Dependency Graph with `networkx`

```python
import networkx as nx

def build_dependency_graph(parsed_data: dict) -> nx.DiGraph:
    """Build cell dependency graph for lineage tracking."""
    G = nx.DiGraph()
    
    for sheet in parsed_data.get('sheets', []):
        for cell in sheet.get('cells', []):
            if cell.get('formula'):
                refs = parse_formula_references(cell['formula'])
                for ref in refs:
                    # Edge: ref → cell (ref affects cell)
                    G.add_edge(ref, cell['address'])
    
    return G

def detect_circular_refs(G: nx.DiGraph) -> list:
    """Detect circular references."""
    return list(nx.simple_cycles(G))

def get_cell_ancestors(G: nx.DiGraph, cell: str) -> set:
    """Get all cells that affect this cell."""
    return nx.ancestors(G, cell)
```

### Token Compression (SpreadsheetLLM)

```python
def compress_for_claude(sheet_data: dict) -> dict:
    """Apply SpreadsheetLLM compression concepts to reduce tokens by 50-70%."""
    return {
        # Structural anchors - headers define structure
        "headers": {
            "row_1": extract_header_cells(sheet_data, row=1),
            "col_A": extract_label_column(sheet_data, col='A')
        },
        # Inverted index - unique labels only
        "unique_labels": list(set(get_all_labels(sheet_data))),
        # Aggregated structure - not all cells
        "structure": [
            {"row": r, "label": l, "bold": b, "indent": i}
            for r, l, b, i in get_label_rows(sheet_data)
        ],
        # Sample values - not all periods
        "sample_values": get_first_period_values(sheet_data)
    }
```

## The 5-Stage Pipeline

### Stage 1: Guided Parsing

```python
PARSING_PROMPT = """
You are parsing an Excel financial model. Extract ALL data with full context.

For each sheet, provide:
- sheet_name: exact name
- sheet_type_guess: income_statement, balance_sheet, cash_flow, 
  debt_schedule, assumptions, scratch, other
- layout: 'time_across_columns' or 'time_down_rows'

For each cell with data:
- address: e.g., "B15"
- raw_value: displayed value
- formula: if formula, the formula text
- references: cells this formula references
- data_type: 'number', 'text', 'date', 'percentage', 'currency'
- formatting: {bold, indent, background}
- cell_type: 'label', 'input', 'calculation', 'output', 'header'

Return as structured JSON.
"""

async def stage_parsing(file_bytes: bytes) -> ParsedModel:
    response = await claude.messages.create(
        model="claude-sonnet-4-20250514",
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "data": file_bytes}},
                {"type": "text", "text": PARSING_PROMPT}
            ]
        }]
    )
    
    parsed = json.loads(response.content[0].text)
    
    # We add dependency graph (deterministic)
    parsed['dependency_graph'] = build_dependency_graph(parsed)
    
    # Emit lineage
    emit_lineage(stage='parsing', action='parsed', output=parsed)
    
    return ParsedModel(**parsed)
```

### Stage 2: Guided Triage

```python
TRIAGE_PROMPT = """
Classify each sheet into tiers:

TIER 1 - PROCESS_HIGH (target 95% accuracy):
- Income Statement / P&L
- Balance Sheet
- Cash Flow Statement

TIER 2 - PROCESS_MEDIUM (target 85% accuracy):
- Debt Schedule
- Depreciation & Amortization
- Working Capital

TIER 3 - PROCESS_LOW (target 70% accuracy):
- Revenue Build
- Assumptions / Drivers
- Sensitivity / Scenarios

TIER 4 - SKIP:
- Names containing: scratch, temp, old, backup, draft
- Chart-only sheets
- Sheets with "DO NOT USE"

For each sheet return:
{
  "sheet_name": str,
  "tier": 1-4,
  "decision": "PROCESS_HIGH" | "PROCESS_MEDIUM" | "PROCESS_LOW" | "SKIP",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}
"""
```

### Stage 3: Guided Structure

```python
STRUCTURE_PROMPT = """
Identify structure of this {sheet_type}.

SECTIONS for Income Statement:
- revenue, cogs, gross_profit, opex, ebitda, depreciation, 
  ebit, interest, ebt, taxes, net_income

SECTIONS for Balance Sheet:
- current_assets, non_current_assets, total_assets,
  current_liabilities, non_current_liabilities, equity

PERIODS:
- Identify columns/rows as: FY, Q, M, LTM
- Mark historical vs. projected

HIERARCHY:
- Level 0: Headers (bold, no values)
- Level 1: Major line items
- Level 2+: Sub-items (indented)

Return structure with sections, periods, line items.
"""
```

### Stage 4: Guided Mapping

```python
MAPPING_PROMPT = """
Map line items to canonical taxonomy.

TAXONOMY:
{taxonomy_json}

ENTITY CONTEXT:
- Entity: {entity_name}
- Industry: {entity_industry}
- Previous patterns from this entity:
{entity_patterns}

MAPPING RULES:
1. Exact match first
2. Semantic match if meaning is clear
3. Consider hierarchy context
4. Consider formula context
5. If uncertain, provide alternatives

For each item return:
{
  "line_item_id": str,
  "original_label": str,
  "canonical_name": str or "custom:{name}",
  "confidence": 0.0-1.0,
  "method": "exact" | "semantic" | "hierarchical" | "formula" | "custom",
  "reasoning": "brief explanation",
  "alternatives": [{"name": str, "confidence": float}]
}
"""
```

### Stage 5: Verification

```python
async def stage_verification(extraction: ExtractionResult) -> VerifiedResult:
    # Deterministic checks (Agent 5)
    deterministic = await validator.check_deterministic(extraction)
    
    # Claude reasoning for edge cases
    verification_prompt = build_verification_prompt(extraction, deterministic)
    claude_reasoning = await claude.messages.create(...)
    
    # Merge results
    return merge_verification(deterministic, claude_reasoning)
```

## Pipeline State Machine

```python
class PipelineState(TypedDict):
    job_id: str
    file_id: str
    entity_id: str
    current_stage: str
    progress_percent: int
    
    # Stage outputs
    parsed: Optional[ParsedModel]
    triage: Optional[List[TriageResult]]
    structure: Optional[ModelStructure]
    mappings: Optional[List[MappingResult]]
    verification: Optional[VerificationResult]
    
    # Tracking
    stage_times: Dict[str, float]
    claude_costs: Dict[str, float]
    errors: List[str]
```

## Error Handling

```python
async def call_claude_with_retry(prompt: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = await claude.messages.create(...)
            return response
        except RateLimitError:
            await asyncio.sleep(2 ** attempt)
        except InvalidResponseError:
            # Log and retry with clearer prompt
            prompt = add_format_reminder(prompt)
    
    raise ExtractionError("Claude unavailable after retries")
```

## Success Criteria

- [ ] All 5 stages execute reliably
- [ ] Processing time < 10 min (subsequent models)
- [ ] Lineage emitted at every stage
- [ ] Errors are recoverable (retry works)
- [ ] Cost tracking accurate to ±5%

---

# Agent 4: Guidelines Manager

## Your Mission

Maintain the domain expertise that guides Claude. You're the keeper of our knowledge.

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D4.1 | Prompt template system | Week 4 | P0 |
| D4.2 | Canonical taxonomy (100+ items) | Week 4 | P0 |
| D4.3 | Entity pattern storage/retrieval | Week 5 | P0 |
| D4.4 | Tier definitions | Week 5 | P0 |
| D4.5 | Prompt versioning | Week 6 | P1 |
| D4.6 | Pattern learning from corrections | Week 7 | P0 |
| D4.7 | A/B testing framework | Week 8 | P2 |

## Canonical Taxonomy Structure

```python
@dataclass
class TaxonomyItem:
    canonical_name: str          # e.g., "revenue"
    category: str                # e.g., "income_statement"
    display_name: str            # e.g., "Revenue"
    aliases: List[str]           # e.g., ["Sales", "Net Sales", "Turnover"]
    definition: str              # Clear definition
    typical_sign: str            # "positive" or "negative"
    parent: Optional[str]        # For hierarchy
    derivation: Optional[str]    # e.g., "gross_profit = revenue - cogs"

# Example taxonomy
TAXONOMY = [
    # Income Statement
    TaxonomyItem("revenue", "income_statement", "Revenue",
                 aliases=["Sales", "Net Sales", "Turnover", "Total Revenue", "Net Revenue"],
                 definition="Total income from primary business activities",
                 typical_sign="positive"),
    
    TaxonomyItem("cogs", "income_statement", "Cost of Goods Sold",
                 aliases=["Cost of Sales", "COS", "Direct Costs", "Cost of Revenue"],
                 definition="Direct costs attributable to goods/services sold",
                 typical_sign="positive"),
    
    TaxonomyItem("gross_profit", "income_statement", "Gross Profit",
                 aliases=["Gross Margin", "GP"],
                 definition="Revenue minus cost of goods sold",
                 typical_sign="positive",
                 derivation="revenue - cogs"),
    
    TaxonomyItem("ebitda", "income_statement", "EBITDA",
                 aliases=["Operating Profit before D&A", "Adjusted EBITDA"],
                 definition="Earnings before interest, taxes, depreciation, amortization",
                 typical_sign="positive"),
    
    # Balance Sheet
    TaxonomyItem("total_assets", "balance_sheet", "Total Assets",
                 aliases=["Assets", "Total Asset"],
                 definition="Sum of all assets",
                 typical_sign="positive"),
    
    TaxonomyItem("total_liabilities", "balance_sheet", "Total Liabilities",
                 aliases=["Liabilities", "Total Liability"],
                 definition="Sum of all liabilities",
                 typical_sign="positive"),
    
    # ... 100+ items total
]
```

## Entity Pattern System

```python
class EntityPatternManager:
    """
    Learn and retrieve entity-specific patterns.
    """
    
    async def get_patterns(self, entity_id: UUID) -> List[EntityPattern]:
        """Get all learned patterns for an entity."""
        return await db.fetch(
            "SELECT * FROM entity_patterns WHERE entity_id = $1 ORDER BY confidence DESC",
            entity_id
        )
    
    async def add_pattern(
        self, 
        entity_id: UUID, 
        original_label: str, 
        canonical_name: str,
        source: str  # 'claude' or 'user_correction'
    ):
        """Add or update a pattern."""
        existing = await self.find_pattern(entity_id, original_label)
        
        if existing:
            # Increment occurrence, update confidence
            await db.execute("""
                UPDATE entity_patterns 
                SET occurrence_count = occurrence_count + 1,
                    confidence = LEAST(confidence + 0.05, 1.0),
                    last_seen = NOW()
                WHERE id = $1
            """, existing.id)
        else:
            await db.execute("""
                INSERT INTO entity_patterns 
                (entity_id, original_label, canonical_name, confidence, created_by)
                VALUES ($1, $2, $3, $4, $5)
            """, entity_id, original_label, canonical_name, 0.8, source)
    
    async def learn_from_correction(
        self, 
        entity_id: UUID,
        original_label: str,
        corrected_canonical: str
    ):
        """Learn from user correction (high confidence)."""
        await self.add_pattern(
            entity_id, 
            original_label, 
            corrected_canonical,
            source='user_correction'
        )
        # User corrections start at higher confidence
        await db.execute("""
            UPDATE entity_patterns 
            SET confidence = 0.95
            WHERE entity_id = $1 AND original_label = $2
        """, entity_id, original_label)
```

## Prompt Versioning

```python
class PromptManager:
    """Version and manage prompt templates."""
    
    def __init__(self):
        self.prompts = {
            'parsing': {'v1': PARSING_PROMPT_V1, 'v2': PARSING_PROMPT_V2},
            'triage': {'v1': TRIAGE_PROMPT_V1},
            'structure': {'v1': STRUCTURE_PROMPT_V1},
            'mapping': {'v1': MAPPING_PROMPT_V1},
            'verification': {'v1': VERIFICATION_PROMPT_V1}
        }
        self.active_versions = {
            'parsing': 'v1',
            'triage': 'v1',
            'structure': 'v1',
            'mapping': 'v1',
            'verification': 'v1'
        }
    
    def get_prompt(self, stage: str) -> str:
        version = self.active_versions[stage]
        return self.prompts[stage][version]
    
    def format_mapping_prompt(
        self, 
        line_items: List[dict],
        entity_id: UUID
    ) -> str:
        """Build mapping prompt with entity context."""
        template = self.get_prompt('mapping')
        patterns = entity_patterns.get_patterns(entity_id)
        entity = get_entity(entity_id)
        
        return template.format(
            taxonomy_json=json.dumps(TAXONOMY),
            entity_name=entity.name,
            entity_industry=entity.industry,
            entity_patterns=json.dumps(patterns),
            line_items=json.dumps(line_items)
        )
```

## Success Criteria

- [ ] Taxonomy covers 100+ financial line items
- [ ] Entity patterns retrieved in <50ms
- [ ] Patterns improve accuracy after 5+ models from same entity
- [ ] Prompts are versioned and auditable

---

# Agent 5: Validator

## Your Mission

Ensure extracted data is correct and consistent using both deterministic checks and guided reasoning.

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D5.1 | Format validation | Week 6 | P0 |
| D5.2 | Balance sheet balance check | Week 6 | P0 |
| D5.3 | Derivation consistency checks | Week 6 | P0 |
| D5.4 | Sign convention checks | Week 7 | P0 |
| D5.5 | Cross-period validation | Week 7 | P1 |
| D5.6 | Claude reasoning integration | Week 7 | P0 |
| D5.7 | Composite confidence scoring | Week 8 | P0 |

## Validation Rules

```python
class DeterministicValidator:
    """Rules that always apply, no exceptions."""
    
    def check_balance_sheet_balances(self, extraction: ExtractionResult) -> CheckResult:
        """Total Assets MUST equal Total Liabilities + Equity."""
        assets = extraction.get_value('total_assets')
        liabilities = extraction.get_value('total_liabilities')
        equity = extraction.get_value('total_equity')
        
        if assets is None or liabilities is None or equity is None:
            return CheckResult(status='skipped', reason='Missing values')
        
        expected = liabilities + equity
        variance = abs(assets - expected) / assets if assets != 0 else 0
        
        if variance < 0.0001:  # 0.01% tolerance for rounding
            return CheckResult(status='passed')
        else:
            return CheckResult(
                status='failed',
                expected=expected,
                actual=assets,
                variance_pct=variance * 100,
                message=f"Balance sheet imbalance: {variance*100:.2f}%"
            )
    
    def check_derivation(
        self, 
        extraction: ExtractionResult,
        derived: str,
        formula: str
    ) -> CheckResult:
        """Check that derived values match their formula."""
        # Example: gross_profit = revenue - cogs
        actual = extraction.get_value(derived)
        components = parse_formula(formula)  # {'revenue': 1, 'cogs': -1}
        
        expected = sum(
            extraction.get_value(name) * coef 
            for name, coef in components.items()
        )
        
        variance = abs(actual - expected) / abs(expected) if expected != 0 else 0
        
        if variance < 0.001:  # 0.1% tolerance
            return CheckResult(status='passed')
        else:
            return CheckResult(
                status='warning',
                expected=expected,
                actual=actual,
                message=f"{derived} derivation mismatch"
            )
    
    DERIVATION_RULES = [
        ('gross_profit', 'revenue - cogs'),
        ('ebit', 'ebitda - depreciation - amortization'),
        ('ebt', 'ebit - interest_expense'),
        ('net_income', 'ebt - taxes'),
    ]
```

## Claude Reasoning Integration

```python
VERIFICATION_PROMPT = """
Review these validation results and provide reasoning.

EXTRACTION DATA:
{extraction_summary}

DETERMINISTIC CHECK RESULTS:
{check_results}

For each failed or warning check:
1. Is this a real error or a valid edge case?
2. What might explain this discrepancy?
3. Should this be flagged for human review?

Common valid exceptions:
- Projected periods may not balance (plug not modeled)
- Adjusted metrics exclude one-time items
- Different fiscal year ends cause comparison issues

Return:
{
  "analysis": [
    {
      "check": str,
      "is_real_error": bool,
      "explanation": str,
      "recommend_review": bool
    }
  ],
  "overall_confidence_adjustment": float (-0.2 to +0.1)
}
"""
```

## Composite Confidence

```python
def calculate_composite_confidence(
    mapping_confidence: float,
    validation_result: ValidationResult,
    claude_adjustment: float
) -> float:
    """Calculate final confidence score."""
    
    # Start with mapping confidence
    confidence = mapping_confidence
    
    # Adjust for validation failures
    if validation_result.has_failures:
        confidence -= 0.15
    elif validation_result.has_warnings:
        confidence -= 0.05
    
    # Apply Claude's reasoning adjustment
    confidence += claude_adjustment
    
    # Clamp to valid range
    return max(0.0, min(1.0, confidence))
```

## Success Criteria

- [ ] BS balance check catches 100% of imbalances
- [ ] Derivation checks catch >95% of inconsistencies
- [ ] False positive rate <10%
- [ ] Claude reasoning adds value for edge cases

---

# Agent 6: Lineage Tracker (EXISTENTIAL)

## Your Mission

Ensure 100% lineage completeness. Every value must trace to its source. This is non-negotiable.

## Why This Is Existential

> "If I can click a number and see where it came from, I'm sold." — Marcus (Partner)

Without lineage, no trust. Without trust, no adoption.

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D6.1 | Lineage event schema | Week 3 | P0 |
| D6.2 | Event emission library | Week 4 | P0 |
| D6.3 | Event persistence | Week 4 | P0 |
| D6.4 | Provenance chain builder | Week 5 | P0 |
| D6.5 | Lineage query API | Week 5 | P0 |
| D6.6 | Completeness validator | Week 6 | P0 |
| D6.7 | Audit export | Week 8 | P1 |

## Event Emission Library

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

@dataclass
class LineageEvent:
    id: UUID
    timestamp: datetime
    actor_type: str      # 'system', 'claude', 'user'
    actor_id: str
    action: str          # 'parsed', 'triaged', 'mapped', 'validated', 'corrected'
    stage: str           # 'parsing', 'triage', 'structure', 'mapping', 'verification'
    target_type: str     # 'sheet', 'cell', 'line_item', 'mapping'
    target_id: UUID
    input_snapshot: Dict[str, Any]
    output_snapshot: Dict[str, Any]
    source_file_id: UUID
    source_sheet: Optional[str]
    source_cell: Optional[str]
    confidence: Optional[float]
    claude_reasoning: Optional[str]

class LineageEmitter:
    """All agents use this to emit lineage events."""
    
    async def emit(
        self,
        action: str,
        stage: str,
        target_type: str,
        target_id: UUID,
        input_data: Dict,
        output_data: Dict,
        source_file_id: UUID,
        source_sheet: str = None,
        source_cell: str = None,
        confidence: float = None,
        claude_reasoning: str = None,
        actor_type: str = 'system',
        actor_id: str = None
    ):
        event = LineageEvent(
            id=uuid4(),
            timestamp=datetime.utcnow(),
            actor_type=actor_type,
            actor_id=actor_id or self.get_current_agent(),
            action=action,
            stage=stage,
            target_type=target_type,
            target_id=target_id,
            input_snapshot=input_data,
            output_snapshot=output_data,
            source_file_id=source_file_id,
            source_sheet=source_sheet,
            source_cell=source_cell,
            confidence=confidence,
            claude_reasoning=claude_reasoning
        )
        
        await self.persist(event)
        return event

# Global emitter instance
lineage = LineageEmitter()

# Usage in Agent 3 (Extraction Orchestrator):
await lineage.emit(
    action='mapped',
    stage='mapping',
    target_type='line_item',
    target_id=line_item.id,
    input_data={'original_label': line_item.label},
    output_data={'canonical_name': 'revenue', 'confidence': 0.95},
    source_file_id=file_id,
    source_sheet='P&L',
    source_cell='A15',
    confidence=0.95,
    claude_reasoning='Exact match with alias "Net Sales"',
    actor_type='claude'
)
```

## Provenance Query

```python
class ProvenanceBuilder:
    """Build complete provenance chain for any value."""
    
    async def get_provenance(self, value_id: UUID) -> ProvenanceChain:
        # Get all events for this value
        events = await db.fetch("""
            SELECT * FROM lineage_events 
            WHERE target_id = $1 
            ORDER BY timestamp ASC
        """, value_id)
        
        # Build chain
        chain = []
        for event in events:
            chain.append({
                'step': len(chain) + 1,
                'stage': event.stage,
                'action': event.action,
                'actor': event.actor_type,
                'timestamp': event.timestamp.isoformat(),
                'source': {
                    'file': await self.get_filename(event.source_file_id),
                    'sheet': event.source_sheet,
                    'cell': event.source_cell
                },
                'confidence': event.confidence,
                'reasoning': event.claude_reasoning
            })
        
        return ProvenanceChain(
            value_id=value_id,
            chain=chain
        )
```

## Completeness Validator

```python
class CompletenessValidator:
    """Ensure 100% lineage coverage."""
    
    async def validate_extraction(self, file_id: UUID) -> ValidationResult:
        # Get all extracted values
        values = await db.fetch(
            "SELECT id FROM extracted_values WHERE file_id = $1", 
            file_id
        )
        
        # Check each has lineage
        missing = []
        for value in values:
            events = await db.fetch(
                "SELECT COUNT(*) FROM lineage_events WHERE target_id = $1",
                value.id
            )
            if events[0].count == 0:
                missing.append(value.id)
        
        if missing:
            raise LineageIncompleteError(
                f"Missing lineage for {len(missing)} values: {missing[:5]}..."
            )
        
        return ValidationResult(
            status='complete',
            total_values=len(values),
            events_count=await self.count_events(file_id)
        )
```

## Success Criteria

- [ ] **100% lineage completeness** (existential)
- [ ] Provenance query <500ms
- [ ] Completeness validator runs after every extraction
- [ ] Audit export works for compliance

---

# Agent 7: Confidence Calibrator

## Your Mission

Ensure confidence scores match actual accuracy. A 90% score should mean 90% are correct.

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D7.1 | Confidence score collection | Week 6 | P0 |
| D7.2 | Ground truth tracking | Week 6 | P0 |
| D7.3 | Calibration calculation (ECE) | Week 7 | P0 |
| D7.4 | Threshold management | Week 7 | P0 |
| D7.5 | Calibration monitoring | Week 8 | P1 |

## Calibration Logic

```python
class ConfidenceCalibrator:
    """Calibrate confidence scores to match actual accuracy."""
    
    def __init__(self):
        self.thresholds = {
            'auto_approve': 0.90,
            'suggest_review': 0.70,
            'require_review': 0.50
        }
    
    async def calibrate(
        self, 
        raw_confidence: float,
        mapping_method: str
    ) -> CalibratedConfidence:
        # Get historical accuracy for this method
        historical = await self.get_historical_accuracy(mapping_method)
        
        # Simple calibration: adjust based on historical performance
        if historical:
            calibrated = raw_confidence * historical.accuracy_ratio
        else:
            calibrated = raw_confidence * 0.9  # Conservative default
        
        # Determine action
        if calibrated >= self.thresholds['auto_approve']:
            action = 'auto_approve'
        elif calibrated >= self.thresholds['suggest_review']:
            action = 'suggest_review'
        else:
            action = 'require_review'
        
        return CalibratedConfidence(
            raw=raw_confidence,
            calibrated=calibrated,
            action=action
        )
    
    async def learn_from_correction(
        self,
        mapping_id: UUID,
        was_correct: bool,
        original_confidence: float,
        method: str
    ):
        """Update calibration based on user feedback."""
        await db.execute("""
            INSERT INTO calibration_data 
            (mapping_id, was_correct, confidence, method, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
        """, mapping_id, was_correct, original_confidence, method)
        
        # Recalibrate periodically
        if await self.should_recalibrate():
            await self.recalibrate()
    
    async def calculate_ece(self) -> float:
        """Calculate Expected Calibration Error."""
        # Bucket predictions by confidence
        buckets = await db.fetch("""
            SELECT 
                FLOOR(confidence * 10) / 10 as bucket,
                AVG(confidence) as avg_confidence,
                AVG(CASE WHEN was_correct THEN 1.0 ELSE 0.0 END) as actual_accuracy,
                COUNT(*) as count
            FROM calibration_data
            GROUP BY bucket
        """)
        
        total = sum(b.count for b in buckets)
        ece = sum(
            (b.count / total) * abs(b.avg_confidence - b.actual_accuracy)
            for b in buckets
        )
        
        return ece
```

## Success Criteria

- [ ] ECE < 0.05
- [ ] Auto-approve accuracy > 95%
- [ ] Review rate < 15%
- [ ] Calibration improves with data

---

# Agent 8: Excel Add-in (EXISTENTIAL)

## Your Mission

Build the Excel add-in analysts will love. This is the adoption gateway.

## Why This Is Existential

> "Just make it work in Excel. I don't want to learn another tool." — Sarah (Associate)

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D8.1 | Office.js project scaffold | Week 9 | P0 |
| D8.2 | Authentication flow | Week 9 | P0 |
| D8.3 | Task pane UI | Week 9 | P0 |
| D8.4 | File upload flow | Week 10 | P0 |
| D8.5 | Progress display (SSE) | Week 10 | P0 |
| D8.6 | Results summary | Week 10 | P0 |
| D8.7 | Data import to worksheet | Week 10 | P0 |
| D8.8 | **Provenance panel** | Week 11 | **P0** |
| D8.9 | Custom functions | Week 11 | P0 |
| D8.10 | Cross-platform testing | Week 12 | P0 |

## Technology Stack

**Core Framework:**
```
Office.js (Office Add-ins JavaScript API)
├── React for task pane UI
├── Fluent UI for Microsoft-consistent styling
└── TypeScript recommended
```

**Reference Implementation:**
- **LLMExcel** (github.com/liminityab/LLMExcel) - Open source Excel add-in for GPT/Claude
  - Study their task pane architecture
  - Reference their Excel ↔ LLM communication patterns
  - Note their cell selection handling

**Alternative for Desktop-Only:**
- **xlwings** - Python library that can run inside Excel
  - Pros: Python ecosystem, easier for backend devs
  - Cons: Desktop only, no Excel Online support

**Key Office.js APIs:**
```javascript
// Read cell data
const range = context.workbook.worksheets.getActiveWorksheet()
    .getRange("A1:Z100");
range.load("values, formulas, format");
await context.sync();

// Access formatting
const isBold = range.format.font.bold;
const indent = range.format.indentLevel;

// Custom functions (for =GETMETRIC())
CustomFunctions.associate("GETMETRIC", getMetricHandler);
```

## User Journey

```
1. Open Excel → Click add-in icon
2. Task pane opens → Authenticated (SSO if enterprise)
3. Click "Extract Model" → Select current workbook or browse
4. Progress bar: Parsing... Analyzing... Mapping... Validating...
5. Complete: "Extracted 127 values. 112 auto-approved, 15 need review."
6. Click "Import to Sheet" → Data in new worksheet
7. Click any cell → Provenance panel shows source
8. Type =GETMETRIC("revenue", "2024") → Value appears
9. Low-confidence cells highlighted yellow
10. Click "Review Queue" → Opens dashboard in browser
```

## Provenance Panel

```
┌─────────────────────────────────────────────┐
│ PROVENANCE                              [X] │
├─────────────────────────────────────────────┤
│ Value: €5,200,000                          │
│ Metric: EBITDA                             │
│ Period: FY2024                             │
│ Confidence: 94% ●●●●●●●●●○                 │
├─────────────────────────────────────────────┤
│ SOURCE                                      │
│ File: ThermoStore Model v3.xlsx            │
│ Sheet: P&L                                  │
│ Cell: B42                                   │
│ Original: "Operating Profit before D&A"    │
├─────────────────────────────────────────────┤
│ MAPPING                                     │
│ Method: Semantic match                      │
│ Reasoning: "Operating Profit before D&A    │
│ is a common alias for EBITDA"              │
├─────────────────────────────────────────────┤
│ VALIDATION                                  │
│ ✓ Format check passed                      │
│ ✓ Derivation consistent                    │
├─────────────────────────────────────────────┤
│ [Open in Dashboard] [Report Issue]          │
└─────────────────────────────────────────────┘
```

## Custom Functions

```javascript
/**
 * Get a metric value from the warehouse.
 * @customfunction
 * @param entity Entity name or ID
 * @param metric Canonical metric name
 * @param period Period (e.g., "FY2024", "Q1 2024")
 * @returns The metric value
 */
async function GETMETRIC(entity, metric, period) {
    const response = await fetch(
        `${API_BASE}/entities/${entity}/metrics/${metric}?period=${period}`
    );
    const data = await response.json();
    return data.value;
}

/**
 * Get confidence score for a cell.
 * @customfunction
 * @param cell Cell reference
 * @returns Confidence score (0-1)
 */
function CONFIDENCE(cell) {
    const valueId = getCellValueId(cell);
    return getConfidence(valueId);
}

/**
 * Get source description for a cell.
 * @customfunction
 * @param cell Cell reference
 * @returns Source string
 */
function SOURCE(cell) {
    const valueId = getCellValueId(cell);
    const provenance = getProvenance(valueId);
    return `${provenance.file} | ${provenance.sheet} | ${provenance.cell}`;
}
```

## Success Criteria

- [ ] Add-in loads in <3 seconds
- [ ] File upload → data available in <10 minutes
- [ ] **Provenance lookup <1 second**
- [ ] Works on Windows, Mac, Excel Online
- [ ] Custom functions reliable

---

# Agent 9: Review Dashboard

## Your Mission

Enable fast review and corrections. <3 clicks to correct.

## Your Deliverables

| ID | Deliverable | Due | Priority |
|----|-------------|-----|----------|
| D9.1 | React app scaffold | Week 9 | P0 |
| D9.2 | Authentication | Week 9 | P0 |
| D9.3 | Model list view | Week 9 | P0 |
| D9.4 | Review queue | Week 10 | P0 |
| D9.5 | Correction interface | Week 10 | P0 |
| D9.6 | Bulk actions | Week 11 | P1 |
| D9.7 | System health | Week 11 | P1 |
| D9.8 | Calibration metrics | Week 12 | P1 |

## Review Queue Interface

```
┌─────────────────────────────────────────────────────────────────────────┐
│ REVIEW QUEUE                                    [Approve All] [Refresh] │
├─────────────────────────────────────────────────────────────────────────┤
│ 15 items need review                            Sort: [Priority ▼]     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ ThermoStore | "Operating Costs YoY" → ???                          │ │
│ │ Confidence: 45%  |  Sheet: P&L  |  Cell: B28                       │ │
│ │                                                                     │ │
│ │ Claude's reasoning: "Label suggests year-over-year change in       │ │
│ │ operating costs, but this could be growth rate or absolute value"  │ │
│ │                                                                     │ │
│ │ Suggestions:                                                        │ │
│ │  ○ opex_growth (35%)                                               │ │
│ │  ○ operating_expenses (30%)                                        │ │
│ │  ○ custom: [____________]                                          │ │
│ │                                                                     │ │
│ │ □ Apply to all "Operating Costs YoY" from ThermoStore              │ │
│ │                                                                     │ │
│ │ [Skip] [Approve Selected]                                          │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Correction Flow

```
User selects correct mapping
    ↓
Dashboard calls POST /api/v1/mappings/{id}/correct
    ↓
Agent 6 emits correction lineage event
    ↓
Agent 4 updates entity patterns
    ↓
Agent 7 updates calibration data
    ↓
Next extraction benefits from correction
```

## Success Criteria

- [ ] Review queue loads in <2 seconds
- [ ] **Correction: <3 clicks**
- [ ] Bulk approve works
- [ ] Entity pattern learning visible

---

# Cross-Agent Coordination

## Lineage Emission Responsibility

**Every agent that transforms data MUST emit lineage events.**

| Agent | Events to Emit |
|-------|----------------|
| 3 (Orchestrator) | `parsed`, `triaged`, `structured`, `mapped` |
| 5 (Validator) | `validated`, `flagged` |
| 7 (Calibrator) | `calibrated` |
| 9 (Dashboard) | `corrected`, `approved` |

## Integration Test Schedule

| Week | Test | Agents |
|------|------|--------|
| 5 | Guided extraction E2E | 3, 4 |
| 6 | Extraction + validation | 3, 4, 5 |
| 7 | Full pipeline + lineage | 3, 4, 5, 6, 7 |
| 10 | Add-in + API | 2, 8 |
| 11 | Dashboard + corrections | 9, 4, 6, 7 |
| 12 | Complete system | All |

---

*Agent Kickoff Briefs v3.0 — Guided Hybrid Architecture — February 19, 2026*
