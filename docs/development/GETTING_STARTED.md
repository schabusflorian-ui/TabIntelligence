# Getting Started Guide

## Week 1 Sprint Plan — Guided Hybrid Architecture

---

## Day 1: Setup & Alignment

### Morning: Team Kickoff (2 hours)

**Attendees:** All engineers + PM

**Agenda:**
1. **Product Vision** (15 min)
   - Demo the problem: Show messy Excel model, explain manual extraction pain
   - Show the vision: "Click → Extract → Provenance"

2. **Architecture Overview** (30 min)
   - Walk through the 5-stage guided pipeline
   - Explain: "We guide, Claude extracts, we persist"
   - Show agent organization diagram

3. **Role Assignments** (15 min)
   - Backend #1: Agents 1, 2 (Foundation)
   - Backend #2: Agents 3, 4, 5, 7 (Extraction Engine)
   - Full-stack: Agents 8, 9 (UI) — starts Week 9
   - Lineage: Shared responsibility

4. **Week 1 Goals** (15 min)
   - DB schema designed and created
   - API scaffold running
   - Taxonomy draft (50+ items)
   - Claude proof-of-concept working

5. **Technical Decisions** (30 min)
   - Confirm tech stack
   - Set up repositories
   - Agree on conventions

### Afternoon: Environment Setup (All Engineers)

```bash
# Repository setup
git clone <repo>
cd excel-model-intelligence

# Create project structure
mkdir -p src/{api,extraction,guidelines,validation,lineage,models}
mkdir -p tests/{unit,integration}
mkdir -p docs/{architecture,prompts}
mkdir -p scripts

# Python environment
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn sqlalchemy alembic anthropic pytest

# Docker setup
docker-compose up -d postgres redis

# Verify
python -c "import anthropic; print('Claude SDK ready')"
psql postgresql://localhost/emi -c "SELECT 1"
```

---

## Day 1-2: Parallel Workstreams

### Backend #1: Database Schema (Agent 1)

**Goal:** Core tables created, migrations working

```sql
-- Priority 1: Core entities
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID REFERENCES entities(id),
    filename VARCHAR(255) NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64),
    file_size_bytes BIGINT,
    status VARCHAR(50) DEFAULT 'uploaded',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID REFERENCES files(id),
    status VARCHAR(50) DEFAULT 'pending',
    current_stage VARCHAR(50),
    progress_percent INT DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    cost_usd DECIMAL(10, 4)
);

-- Priority 2: Taxonomy
CREATE TABLE taxonomy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50) NOT NULL,
    display_name VARCHAR(255),
    aliases TEXT[],
    definition TEXT,
    typical_sign VARCHAR(10),
    parent_canonical VARCHAR(100)
);

-- Priority 3: Entity patterns (for learning)
CREATE TABLE entity_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID REFERENCES entities(id),
    original_label VARCHAR(500) NOT NULL,
    canonical_name VARCHAR(100) NOT NULL,
    confidence DECIMAL(5, 4) DEFAULT 0.8,
    occurrence_count INT DEFAULT 1,
    source VARCHAR(50), -- 'claude', 'user_correction'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_id, original_label)
);

-- Priority 4: Lineage (design now, implement Week 2)
CREATE TABLE lineage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    actor_type VARCHAR(20) NOT NULL,
    actor_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    stage VARCHAR(50) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id UUID NOT NULL,
    input_snapshot JSONB,
    output_snapshot JSONB,
    source_file_id UUID,
    source_sheet VARCHAR(255),
    source_cell VARCHAR(20),
    confidence DECIMAL(5, 4),
    claude_reasoning TEXT
);

CREATE INDEX idx_lineage_target ON lineage_events(target_id);
CREATE INDEX idx_lineage_file ON lineage_events(source_file_id);
```

**Deliverable:** `alembic upgrade head` works, tables created

---

### Backend #1: API Scaffold (Agent 2)

**Goal:** FastAPI running with basic endpoints

```python
# src/api/main.py
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(
    title="Excel Model Intelligence",
    version="0.1.0",
    description="Guided hybrid extraction platform"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}

@app.post("/api/v1/files/upload")
async def upload_file(file: UploadFile, entity_id: str = None):
    """Upload Excel file for processing."""
    # Week 1: Just accept and store
    # TODO: S3 upload, job creation
    return {
        "file_id": "placeholder",
        "job_id": "placeholder",
        "status": "uploaded"
    }

@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job status."""
    # TODO: Implement
    return {"job_id": job_id, "status": "pending"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Deliverable:** `curl localhost:8000/health` returns `{"status": "healthy"}`

---

### Backend #2: Claude Proof-of-Concept (Agent 3)

**Goal:** Prove guided extraction works

```python
# scripts/poc_guided_extraction.py
"""
Proof of concept: Can Claude extract financial data with our guidance?
Run this on Day 1-2 to validate the approach.
"""

import anthropic
import json
import base64
from pathlib import Path

client = anthropic.Anthropic()

# Minimal parsing prompt
PARSING_PROMPT = """
You are parsing an Excel financial model.

For each sheet, identify:
1. sheet_name
2. sheet_type: income_statement, balance_sheet, cash_flow, other
3. For data cells, extract: address, label, value, formula (if any)

Focus on the main financial statements. Skip charts and scratch sheets.

Return as JSON:
{
  "sheets": [
    {
      "name": "...",
      "type": "...",
      "line_items": [
        {"row": 1, "label": "Revenue", "values": {"FY2023": 100, "FY2024": 120}}
      ]
    }
  ]
}
"""

def test_guided_extraction(file_path: str):
    """Test Claude extraction on a sample file."""
    
    # Read file
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    
    file_base64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    
    # Call Claude
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "data": file_base64
                    }
                },
                {
                    "type": "text",
                    "text": PARSING_PROMPT
                }
            ]
        }]
    )
    
    # Parse response
    content = response.content[0].text
    
    # Try to extract JSON
    try:
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        result = json.loads(content)
        return {
            "success": True,
            "result": result,
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            "cost_estimate": (response.usage.input_tokens * 0.003 + response.usage.output_tokens * 0.015) / 1000
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": str(e),
            "raw_content": content
        }

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python poc_guided_extraction.py <excel_file>")
        print("\nThis script validates that Claude can extract financial data.")
        sys.exit(1)
    
    file_path = sys.argv[1]
    print(f"Testing guided extraction on: {file_path}")
    print("-" * 50)
    
    result = test_guided_extraction(file_path)
    
    if result["success"]:
        print("✅ Extraction successful!")
        print(f"Tokens used: {result['tokens_used']}")
        print(f"Cost estimate: ${result['cost_estimate']:.4f}")
        print("\nExtracted structure:")
        print(json.dumps(result["result"], indent=2)[:2000])  # First 2000 chars
    else:
        print("❌ Extraction failed")
        print(f"Error: {result['error']}")
        print(f"Raw content: {result['raw_content'][:500]}")
```

**Deliverable:** Run on any Excel file, get structured JSON back

---

### Backend #2: Initial Taxonomy (Agent 4)

**Goal:** Draft 50+ canonical items

```python
# src/guidelines/taxonomy.py
"""
Canonical taxonomy for financial line items.
Start with core items, expand over time.
"""

TAXONOMY = [
    # === INCOME STATEMENT ===
    # Revenue
    {"canonical_name": "revenue", "category": "income_statement", 
     "display_name": "Revenue",
     "aliases": ["Sales", "Net Sales", "Turnover", "Total Revenue", "Net Revenue", "Revenues"],
     "typical_sign": "positive"},
    
    {"canonical_name": "product_revenue", "category": "income_statement",
     "display_name": "Product Revenue", 
     "aliases": ["Product Sales", "Goods Revenue"],
     "parent": "revenue", "typical_sign": "positive"},
    
    {"canonical_name": "service_revenue", "category": "income_statement",
     "display_name": "Service Revenue",
     "aliases": ["Services", "Service Sales"],
     "parent": "revenue", "typical_sign": "positive"},
    
    # Costs
    {"canonical_name": "cogs", "category": "income_statement",
     "display_name": "Cost of Goods Sold",
     "aliases": ["Cost of Sales", "COS", "COGS", "Direct Costs", "Cost of Revenue"],
     "typical_sign": "positive"},
    
    {"canonical_name": "gross_profit", "category": "income_statement",
     "display_name": "Gross Profit",
     "aliases": ["Gross Margin", "GP"],
     "derivation": "revenue - cogs", "typical_sign": "positive"},
    
    # Operating expenses
    {"canonical_name": "opex", "category": "income_statement",
     "display_name": "Operating Expenses",
     "aliases": ["Operating Costs", "OpEx", "Total Operating Expenses"],
     "typical_sign": "positive"},
    
    {"canonical_name": "sga", "category": "income_statement",
     "display_name": "SG&A",
     "aliases": ["Selling, General & Administrative", "SG&A Expenses", "G&A"],
     "parent": "opex", "typical_sign": "positive"},
    
    {"canonical_name": "rd_expense", "category": "income_statement",
     "display_name": "R&D Expense",
     "aliases": ["Research & Development", "R&D", "Research and Development"],
     "parent": "opex", "typical_sign": "positive"},
    
    {"canonical_name": "sales_marketing", "category": "income_statement",
     "display_name": "Sales & Marketing",
     "aliases": ["S&M", "Marketing Expense", "Selling Expenses"],
     "parent": "opex", "typical_sign": "positive"},
    
    # Profitability
    {"canonical_name": "ebitda", "category": "income_statement",
     "display_name": "EBITDA",
     "aliases": ["Operating Profit before D&A", "Adjusted EBITDA", "EBITDA (Adjusted)"],
     "typical_sign": "positive"},
    
    {"canonical_name": "depreciation", "category": "income_statement",
     "display_name": "Depreciation",
     "aliases": ["D&A", "Depreciation & Amortization", "Depreciation Expense"],
     "typical_sign": "positive"},
    
    {"canonical_name": "amortization", "category": "income_statement",
     "display_name": "Amortization",
     "aliases": ["Amortization Expense", "Intangible Amortization"],
     "typical_sign": "positive"},
    
    {"canonical_name": "ebit", "category": "income_statement",
     "display_name": "EBIT",
     "aliases": ["Operating Income", "Operating Profit", "Income from Operations"],
     "derivation": "ebitda - depreciation - amortization", "typical_sign": "positive"},
    
    {"canonical_name": "interest_expense", "category": "income_statement",
     "display_name": "Interest Expense",
     "aliases": ["Interest", "Interest Charges", "Finance Costs"],
     "typical_sign": "positive"},
    
    {"canonical_name": "interest_income", "category": "income_statement",
     "display_name": "Interest Income",
     "aliases": ["Interest Earned"],
     "typical_sign": "positive"},
    
    {"canonical_name": "ebt", "category": "income_statement",
     "display_name": "EBT",
     "aliases": ["Pre-tax Income", "Income Before Tax", "Profit Before Tax", "PBT"],
     "derivation": "ebit - interest_expense + interest_income", "typical_sign": "positive"},
    
    {"canonical_name": "tax_expense", "category": "income_statement",
     "display_name": "Tax Expense",
     "aliases": ["Income Tax", "Taxes", "Provision for Taxes"],
     "typical_sign": "positive"},
    
    {"canonical_name": "net_income", "category": "income_statement",
     "display_name": "Net Income",
     "aliases": ["Net Profit", "Net Earnings", "Bottom Line", "Profit After Tax"],
     "derivation": "ebt - tax_expense", "typical_sign": "positive"},
    
    # === BALANCE SHEET - ASSETS ===
    {"canonical_name": "cash", "category": "balance_sheet",
     "display_name": "Cash",
     "aliases": ["Cash & Cash Equivalents", "Cash and Equivalents", "Liquidity"],
     "typical_sign": "positive"},
    
    {"canonical_name": "accounts_receivable", "category": "balance_sheet",
     "display_name": "Accounts Receivable",
     "aliases": ["AR", "Receivables", "Trade Receivables"],
     "typical_sign": "positive"},
    
    {"canonical_name": "inventory", "category": "balance_sheet",
     "display_name": "Inventory",
     "aliases": ["Inventories", "Stock"],
     "typical_sign": "positive"},
    
    {"canonical_name": "prepaid_expenses", "category": "balance_sheet",
     "display_name": "Prepaid Expenses",
     "aliases": ["Prepaids", "Prepayments"],
     "typical_sign": "positive"},
    
    {"canonical_name": "current_assets", "category": "balance_sheet",
     "display_name": "Current Assets",
     "aliases": ["Total Current Assets", "Short-term Assets"],
     "typical_sign": "positive"},
    
    {"canonical_name": "ppe", "category": "balance_sheet",
     "display_name": "PP&E",
     "aliases": ["Property, Plant & Equipment", "Fixed Assets", "Tangible Assets"],
     "typical_sign": "positive"},
    
    {"canonical_name": "intangibles", "category": "balance_sheet",
     "display_name": "Intangible Assets",
     "aliases": ["Intangibles", "Goodwill & Intangibles"],
     "typical_sign": "positive"},
    
    {"canonical_name": "goodwill", "category": "balance_sheet",
     "display_name": "Goodwill",
     "aliases": [],
     "typical_sign": "positive"},
    
    {"canonical_name": "non_current_assets", "category": "balance_sheet",
     "display_name": "Non-Current Assets",
     "aliases": ["Long-term Assets", "Fixed Assets"],
     "typical_sign": "positive"},
    
    {"canonical_name": "total_assets", "category": "balance_sheet",
     "display_name": "Total Assets",
     "aliases": ["Assets"],
     "derivation": "current_assets + non_current_assets", "typical_sign": "positive"},
    
    # === BALANCE SHEET - LIABILITIES ===
    {"canonical_name": "accounts_payable", "category": "balance_sheet",
     "display_name": "Accounts Payable",
     "aliases": ["AP", "Payables", "Trade Payables"],
     "typical_sign": "positive"},
    
    {"canonical_name": "accrued_expenses", "category": "balance_sheet",
     "display_name": "Accrued Expenses",
     "aliases": ["Accruals", "Accrued Liabilities"],
     "typical_sign": "positive"},
    
    {"canonical_name": "short_term_debt", "category": "balance_sheet",
     "display_name": "Short-term Debt",
     "aliases": ["Current Debt", "ST Debt", "Current Portion of LT Debt"],
     "typical_sign": "positive"},
    
    {"canonical_name": "current_liabilities", "category": "balance_sheet",
     "display_name": "Current Liabilities",
     "aliases": ["Total Current Liabilities", "Short-term Liabilities"],
     "typical_sign": "positive"},
    
    {"canonical_name": "long_term_debt", "category": "balance_sheet",
     "display_name": "Long-term Debt",
     "aliases": ["LT Debt", "Senior Debt", "Term Loan", "Notes Payable"],
     "typical_sign": "positive"},
    
    {"canonical_name": "total_debt", "category": "balance_sheet",
     "display_name": "Total Debt",
     "aliases": ["Debt", "Borrowings", "Financial Debt"],
     "derivation": "short_term_debt + long_term_debt", "typical_sign": "positive"},
    
    {"canonical_name": "non_current_liabilities", "category": "balance_sheet",
     "display_name": "Non-Current Liabilities",
     "aliases": ["Long-term Liabilities"],
     "typical_sign": "positive"},
    
    {"canonical_name": "total_liabilities", "category": "balance_sheet",
     "display_name": "Total Liabilities",
     "aliases": ["Liabilities"],
     "derivation": "current_liabilities + non_current_liabilities", "typical_sign": "positive"},
    
    # === BALANCE SHEET - EQUITY ===
    {"canonical_name": "common_stock", "category": "balance_sheet",
     "display_name": "Common Stock",
     "aliases": ["Share Capital", "Paid-in Capital"],
     "typical_sign": "positive"},
    
    {"canonical_name": "retained_earnings", "category": "balance_sheet",
     "display_name": "Retained Earnings",
     "aliases": ["Accumulated Earnings", "Retained Profit"],
     "typical_sign": "positive"},
    
    {"canonical_name": "total_equity", "category": "balance_sheet",
     "display_name": "Total Equity",
     "aliases": ["Shareholders' Equity", "Stockholders' Equity", "Net Worth", "Book Value"],
     "typical_sign": "positive"},
    
    # === CASH FLOW ===
    {"canonical_name": "cfo", "category": "cash_flow",
     "display_name": "Cash from Operations",
     "aliases": ["Operating Cash Flow", "CFO", "Cash from Operating Activities"],
     "typical_sign": "positive"},
    
    {"canonical_name": "capex", "category": "cash_flow",
     "display_name": "Capital Expenditures",
     "aliases": ["CapEx", "PP&E Purchases", "Capital Spending"],
     "typical_sign": "negative"},
    
    {"canonical_name": "cfi", "category": "cash_flow",
     "display_name": "Cash from Investing",
     "aliases": ["Investing Cash Flow", "CFI", "Cash from Investing Activities"],
     "typical_sign": "negative"},
    
    {"canonical_name": "cff", "category": "cash_flow",
     "display_name": "Cash from Financing",
     "aliases": ["Financing Cash Flow", "CFF", "Cash from Financing Activities"],
     "typical_sign": "varies"},
    
    {"canonical_name": "fcf", "category": "cash_flow",
     "display_name": "Free Cash Flow",
     "aliases": ["FCF", "Unlevered Free Cash Flow"],
     "derivation": "cfo - capex", "typical_sign": "positive"},
    
    {"canonical_name": "net_change_cash", "category": "cash_flow",
     "display_name": "Net Change in Cash",
     "aliases": ["Change in Cash", "Cash Movement"],
     "derivation": "cfo + cfi + cff", "typical_sign": "varies"},
]

def get_taxonomy():
    """Return the full taxonomy."""
    return TAXONOMY

def get_taxonomy_for_prompt():
    """Return taxonomy formatted for Claude prompt."""
    categories = {}
    for item in TAXONOMY:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "name": item["canonical_name"],
            "display": item["display_name"],
            "aliases": item.get("aliases", [])
        })
    return categories

if __name__ == "__main__":
    import json
    print(f"Taxonomy contains {len(TAXONOMY)} items")
    print(json.dumps(get_taxonomy_for_prompt(), indent=2))
```

**Deliverable:** 50+ taxonomy items defined with aliases

---

## Day 3-5: Integration & First E2E

### Goal: Upload → Claude Extract → Store

```python
# src/extraction/orchestrator.py
"""
Extraction orchestrator - coordinates the 5-stage pipeline.
Week 1: Implement stages 1-2 (parsing, triage)
"""

import anthropic
import json
import base64
from typing import Optional
from dataclasses import dataclass

from src.guidelines.taxonomy import get_taxonomy_for_prompt

client = anthropic.Anthropic()

@dataclass
class ExtractionResult:
    file_id: str
    sheets: list
    triage: list
    raw_response: str
    tokens_used: int
    cost_usd: float

PARSING_PROMPT = """
You are parsing an Excel financial model. Extract ALL data with full context.

For each sheet, provide:
- sheet_name: exact name
- sheet_type_guess: income_statement, balance_sheet, cash_flow, debt_schedule, assumptions, scratch, other
- layout: 'time_across_columns' or 'time_down_rows'
- periods: list of column/row headers that are time periods
- line_items: array of extracted rows

For each line item:
- row_index: row number
- label: the text label
- hierarchy_level: 0=header, 1=main item, 2=sub-item
- values: dict of period -> value
- formula: if it's a formula, note what it references

Return as JSON. Be thorough - extract everything.
"""

TRIAGE_PROMPT = """
Based on this parsed model, classify each sheet:

TIER 1 (PROCESS_HIGH): Income Statement, Balance Sheet, Cash Flow
TIER 2 (PROCESS_MEDIUM): Debt Schedule, D&A Schedule, Working Capital
TIER 3 (PROCESS_LOW): Revenue Build, Assumptions, Sensitivity
TIER 4 (SKIP): Scratch, Charts, Backup, Old versions

For each sheet return:
{
  "sheet_name": str,
  "tier": 1-4,
  "decision": "PROCESS_HIGH" | "PROCESS_MEDIUM" | "PROCESS_LOW" | "SKIP",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}

Sheets to classify:
{sheets}
"""

async def stage_1_parsing(file_bytes: bytes) -> dict:
    """Stage 1: Parse Excel with Claude."""
    
    file_base64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "data": file_base64
                    }
                },
                {"type": "text", "text": PARSING_PROMPT}
            ]
        }]
    )
    
    content = response.content[0].text
    
    # Parse JSON from response
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    
    return {
        "parsed": json.loads(content),
        "tokens": response.usage.input_tokens + response.usage.output_tokens
    }

async def stage_2_triage(parsed_result: dict) -> dict:
    """Stage 2: Triage sheets."""
    
    sheets_summary = [
        {"name": s["sheet_name"], "type_guess": s.get("sheet_type_guess")}
        for s in parsed_result["parsed"].get("sheets", [])
    ]
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": TRIAGE_PROMPT.format(sheets=json.dumps(sheets_summary))
        }]
    )
    
    content = response.content[0].text
    
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    
    return {
        "triage": json.loads(content),
        "tokens": response.usage.input_tokens + response.usage.output_tokens
    }

async def extract(file_bytes: bytes, file_id: str) -> ExtractionResult:
    """Run extraction pipeline."""
    
    total_tokens = 0
    
    # Stage 1: Parse
    parse_result = await stage_1_parsing(file_bytes)
    total_tokens += parse_result["tokens"]
    
    # Stage 2: Triage
    triage_result = await stage_2_triage(parse_result)
    total_tokens += triage_result["tokens"]
    
    # Cost estimate (Claude Sonnet pricing)
    cost = total_tokens * 0.003 / 1000  # Simplified
    
    return ExtractionResult(
        file_id=file_id,
        sheets=parse_result["parsed"].get("sheets", []),
        triage=triage_result["triage"],
        raw_response=json.dumps(parse_result["parsed"]),
        tokens_used=total_tokens,
        cost_usd=cost
    )
```

---

## Week 1 Checklist

### By End of Day 2

- [ ] Repository created and shared
- [ ] All engineers have local environment working
- [ ] Database running locally (Docker)
- [ ] Core tables created (entities, files, jobs)
- [ ] FastAPI returns health check

### By End of Day 3

- [ ] Taxonomy with 50+ items defined
- [ ] Claude POC script working on sample file
- [ ] S3 bucket configured (or local MinIO)
- [ ] File upload endpoint stores files

### By End of Day 5

- [ ] Stages 1-2 (parse + triage) working E2E
- [ ] Job status tracking functional
- [ ] Sample extraction stored in database
- [ ] Week 1 demo ready

---

## Week 1 Demo Script

**What to show:**

1. **Upload file** via API
   ```bash
   curl -X POST http://localhost:8000/api/v1/files/upload \
     -F "file=@sample_model.xlsx" \
     -F "entity_id=test-entity"
   ```

2. **Show job status**
   ```bash
   curl http://localhost:8000/api/v1/jobs/{job_id}
   # Returns: {"status": "completed", "stages_completed": ["parsing", "triage"]}
   ```

3. **Show extracted structure**
   - Sheets identified
   - Triage decisions (Tier 1-4)
   - Line items extracted

4. **Show cost**
   - Tokens used
   - Cost estimate

---

## Getting Sample Models

You need 3-5 Excel models for testing. Options:

1. **Create simple test model** (5 min)
   ```
   Sheet 1: "Income Statement" - Revenue, COGS, Gross Profit, etc.
   Sheet 2: "Balance Sheet" - Assets, Liabilities, Equity
   Sheet 3: "Scratch" - Random notes (should be skipped)
   ```

2. **Download free templates**
   - Macabacus templates
   - Wall Street Prep samples
   - Corporate Finance Institute templates

3. **Ask pilot customer** (ideal)
   - "Can we use 3 anonymized models for development?"

---

## Communication Setup

1. **Slack channel:** #excel-intelligence
2. **Daily standup:** 9:00 AM (15 min)
3. **Weekly demo:** Friday 4:00 PM
4. **Status doc:** WEEKLY_STATUS.md in repo

---

## First PR Requirements

Every PR from Day 1 must:

1. Include tests (even basic ones)
2. Update WEEKLY_STATUS.md
3. Follow commit conventions: `feat:`, `fix:`, `docs:`
4. Be reviewed by at least one other engineer

---

## Success Criteria: Week 1

| Criteria | Target |
|----------|--------|
| DB schema | ✅ Core tables created |
| API | ✅ Health + upload endpoints |
| Claude POC | ✅ Extracts data from sample file |
| Taxonomy | ✅ 50+ items defined |
| Triage | ✅ Classifies sheets correctly |
| Demo | ✅ Upload → extract → show results |

---

*Let's build something analysts will love.*
