# DebtFund — Demo Walkthrough Script

> A 20-minute guided demo for potential users. Each act includes talking points, expected screen state, and key moments to pause for questions.

---

## Prerequisites

Before the demo, ensure:

- [ ] Server running at `http://localhost:8000`
- [ ] At least one entity created with 1–2 completed extractions
- [ ] API key configured in the web app (sidebar → key icon)
- [ ] Sample Excel file ready for upload (e.g., `scripts/fixtures/realistic_model.xlsx`)
- [ ] Browser open with DevTools closed, full-screen mode

---

## Act 1: The Problem (3 minutes)

**Setup**: Open a sample Excel financial model in a separate browser tab or show a screenshot.

### Talking Points

> "Every credit fund receives financial models from sponsors — LBO models, operating models, debt schedules. Each one is different."

> "An analyst might spend 2–3 hours extracting the key numbers from a single model into their own templates."

> "And the same line item appears as 'Revenue', 'Total Revenue', 'Net Sales', 'Turnover' — there's no standard vocabulary across sponsors."

> "Once you copy numbers into your analysis, you lose the audit trail. Where did this EBITDA number come from? Which cell? Which sheet?"

> "DebtFund solves all three problems: **speed, standardization, and auditability**."

### Transition

> "Let me show you how it works."

---

## Act 2: Upload & Extraction (5 minutes)

**Navigate to**: Dashboard (`http://localhost:8000/#/`)

### Screen: Dashboard

**Talking Points**:

> "This is the portfolio dashboard. At the top you can see KPIs — total entities, extractions, average confidence across all jobs, and total Claude AI cost."

- Point to the stats grid at the top
- Note the recent extractions table

> "Let's upload a new financial model."

### Action: Upload File

1. Drag the sample `.xlsx` file onto the upload zone
2. Wait for the upload to complete — a toast notification appears with the job ID
3. Click the new extraction in the recent jobs table to navigate to Job Detail

### Screen: Job Detail (Processing)

**Talking Points** — walk through stages as the progress bar advances:

> "The extraction runs through 5 stages, each powered by Claude AI."

| Stage | Progress | What to say |
|-------|----------|-------------|
| Parse | 0–20% | "Stage 1: We read every cell, formula, and formatting cue from the Excel file." |
| Triage | 20–30% | "Stage 2: The AI classifies which sheets are important. P&L and Balance Sheet are Tier 1 — those get full extraction. Assumption tabs are Tier 3 — metadata only." |
| Map | 30–55% | "Stage 3: This is the core. Every label gets mapped to one of 312 canonical financial items. The AI understands that 'Operating Revenue' and 'Net Sales' are both `revenue`." |
| Validate | 55–75% | "Stage 4: Deterministic accounting checks. Does Assets equal Liabilities plus Equity? Does the cash flow reconcile?" |
| Enhanced Map | 75–95% | "Stage 5: Items mapped with low confidence get a second pass with the full extraction context." |

> "The whole process takes under 15 minutes for a first model. Under 8 minutes for subsequent models from the same company, because the system remembers previous mappings."

### Key Moment

When the extraction completes, pause on the quality grade badge:

> "This extraction got a **Grade B** — that means the data is reliable. An A would mean no manual review needed at all."

---

## Act 3: Results Deep Dive (7 minutes)

**Screen**: Job Detail → Line Items tab

### Line Items Table

> "Every extracted data point is here. You can see the canonical name, the original label from Excel, the confidence score, and the values for each period."

**Action**: Click on a row to expand inline provenance:

> "Here's the full audit trail. You can see exactly which cell this came from — sheet name, row, column. You can see the original text and how the AI reasoned about the mapping."

**Action**: Point to a low-confidence item (yellow/orange badge):

> "The AI flagged this one as uncertain. Let me correct it."

**Action**: Click the canonical name cell, show the searchable dropdown:

> "Type a few characters — 'rev' — and you see all revenue-related items. Arrow keys to navigate, Enter to confirm. This correction is now saved as an entity pattern."

### Key Moment — The Learning Story

> "This correction doesn't just fix this extraction — **it teaches the system**. Next time we see this label from this company, it will get it right automatically. That's the compounding data asset."

### Triage Tab

**Action**: Click the "Triage" tab:

> "Sheet-by-sheet classification. You can see which sheets were fully processed and which were skipped. The rationale column explains why."

### Validation Tab

**Action**: Click the "Validation" tab:

> "Accounting checks. Did the balance sheet balance? Did cash flow movements reconcile? Each check shows pass/fail with details."

### Lineage Tab

**Action**: Click the "Lineage" tab:

> "Complete timeline of every pipeline stage — what went in, what came out, how long it took. Full audit trail for compliance."

### Corrections Tab

**Action**: Click the "Corrections" tab:

> "Every correction made to this extraction, with timestamps and undo capability. Nothing is lost."

---

## Act 4: Portfolio Intelligence (3 minutes)

### Analytics Page

**Navigate to**: Analytics (`http://localhost:8000/#/analytics`)

**Portfolio Health tab**:

> "Quality distribution across all extractions. Most of our extractions are Grade A or B — trustworthy data."

**Cross-Entity Compare tab** (if 2+ entities exist):

**Action**: Select 2 entities, enter "revenue" and "ebitda" as canonical names, click Compare:

> "Side-by-side comparison. You can compare a UK company reporting in GBP with a US company in USD — the platform handles FX conversion automatically."

### Entity Detail — Financials

**Navigate to**: Entity Detail → Financials tab:

> "This is the structured financial statement view. Revenue at the top, Net Income at the bottom — just like a real income statement. Children are indented under parents. Subtotals are visually distinct."

> "Each line has a sparkline showing the trend across periods. Negative values appear in red parentheses."

---

## Act 5: Governance (2 minutes)

### Taxonomy Browser

**Navigate to**: Taxonomy (`http://localhost:8000/#/taxonomy`)

> "312 canonical financial items, organized into 6 categories."

**Action**: Click on a category (e.g., Income Statement), expand a few items:

> "Every item has a definition, typical sign convention, aliases, and validation rules. This is the vocabulary that standardizes data across all models."

**Action**: Click the "Suggestions" tab:

> "The system proposes new aliases and items based on what it discovers during extraction. You approve or reject. The taxonomy evolves with usage."

### Entity Patterns

**Navigate to**: Entity Detail → Patterns tab:

> "Over time, each entity builds up a library of learned patterns. This is the compounding data asset — every extraction is faster and more accurate than the last."

---

## Act 6: Technical Confidence (2 minutes)

### System Admin

**Navigate to**: Admin (`http://localhost:8000/#/admin`)

> "Real-time system health. Database connection pool, circuit breaker state, stale job detection."

### API Documentation

**Open**: `http://localhost:8000/docs` in a new tab:

> "50+ REST API endpoints, fully documented with OpenAPI. Every operation you just saw in the UI is also available programmatically."

### Closing Statement

> "Under the hood: **2,555 automated tests**, CI/CD pipeline, Docker deployment, Kubernetes-ready health probes."

> "DebtFund turns the most tedious part of credit analysis — extracting data from Excel models — into a **15-minute automated process** with full auditability. And it **gets smarter with every model you feed it**."

---

## Fallback Plan

If the live system is unavailable during the demo:

1. Open `docs/demo/product-overview.html` in a browser — serves as a visual product walkthrough
2. Reference `docs/demo/architecture-diagrams.md` for technical depth (Mermaid diagrams render in VS Code or GitHub)
3. Use `docs/demo/feature-catalog.md` as a comprehensive capability reference
4. The roadmap (`docs/demo/roadmap.md`) demonstrates future vision

---

## Common Questions & Answers

**Q: What types of Excel models does it handle?**
A: Any .xlsx or .xls file. Optimized for corporate finance (3-statement models, LBOs), debt schedules, and project finance models. Handles messy formatting, merged cells, and inconsistent layouts.

**Q: How accurate is it?**
A: Target >85% accuracy on Tier 1 line items (core financial statements). The quality grade tells you at a glance. Entity patterns improve accuracy over time.

**Q: How much does it cost per extraction?**
A: Target <$0.75 per model in Claude AI costs. Subsequent extractions from the same entity are cheaper due to pattern shortcircuit.

**Q: Can I use it via API only?**
A: Yes. Every feature is available via 50+ REST API endpoints. The web app is entirely built on the same API.

**Q: How does it handle sensitive financial data?**
A: API key authentication with entity scoping, SHA-256 hashing, comprehensive audit logging, and security headers. Files stored in S3 with encryption. No data leaves your infrastructure (self-hosted) or your cloud tenant (SaaS).

**Q: What happens when the AI gets it wrong?**
A: You correct it inline. The correction creates an entity pattern that prevents the same mistake in future extractions. The system learns from every correction.

---

*Document generated for the DebtFund Excel Model Intelligence Platform documentation package.*
