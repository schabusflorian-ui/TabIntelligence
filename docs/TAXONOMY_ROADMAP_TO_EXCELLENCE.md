# Taxonomy System: Roadmap to World-Class Product

**Current Status**: ✅ Solid Foundation (172 items, database-backed, tested)

**Gap Analysis**: What separates "good" from "world-class" product experience

---

## 🎯 Priority 1: Intelligent Learning & Adaptation (Weeks 4-6)

### Issue
- Static taxonomy cannot learn from user corrections
- No entity-specific patterns (every company's "Revenue" looks different)
- Mapping confidence not calibrated to actual accuracy

### World-Class Solution: Self-Improving System

#### A. Entity Pattern Learning (Agent 4 - Week 4)
**What**: System learns company-specific terminology over time

**Implementation**:
```python
# Entity-specific pattern storage
class EntityPatternManager:
    async def learn_from_correction(
        self,
        entity_id: UUID,
        original_label: str,
        correct_canonical: str,
        confidence: float
    ):
        """
        User corrects "Net Revenues" → "revenue" for Company X.
        Next time Company X uploads, "Net Revenues" maps to "revenue"
        with 0.99 confidence automatically.
        """

    async def get_entity_patterns(self, entity_id: UUID) -> List[Pattern]:
        """Returns learned patterns for this entity, sorted by confidence."""

    async def suggest_corrections(self, mappings: List[Mapping]) -> List[Suggestion]:
        """Uses historical patterns to suggest fixes before user sees them."""
```

**Database**:
```sql
-- Already in schema from Agent 1!
CREATE TABLE entity_patterns (
    id UUID PRIMARY KEY,
    entity_id UUID REFERENCES entities(id),
    original_label VARCHAR(500),
    canonical_name VARCHAR(100),
    confidence DECIMAL(5,4),
    occurrence_count INT DEFAULT 1,
    last_seen TIMESTAMPTZ,
    created_by VARCHAR(50)  -- 'claude', 'user_correction', 'ml_model'
);
```

**User Experience**:
```
Upload #1: "Net Revenues" → mapped to "revenue" (confidence: 0.75)
User corrects: "Net Revenues" → "revenue" ✅

Upload #2: "Net Revenues" → AUTOMATICALLY "revenue" (confidence: 0.99)
           System shows: "Learned from your previous correction ✨"
```

**Impact**:
- ✅ 90% reduction in corrections for repeat uploads
- ✅ Entity-specific accuracy improves over time
- ✅ Users feel system "learns" and gets smarter

---

#### B. Confidence Calibration (Agent 7 - Week 6)

**What**: Claude's confidence scores don't match actual accuracy

**The Problem**:
```
Claude says: 0.95 confidence → Actually correct 60% of time (overconfident)
Claude says: 0.70 confidence → Actually correct 80% of time (underconfident)
```

**World-Class Solution**: Expected Calibration Error (ECE) < 0.05

```python
class ConfidenceCalibrator:
    async def calibrate_scores(
        self,
        raw_scores: List[float],
        actual_outcomes: List[bool]
    ) -> List[float]:
        """
        Uses Platt scaling / isotonic regression to calibrate.

        Raw score 0.95 → Calibrated 0.65 (realistic)
        Raw score 0.70 → Calibrated 0.82 (realistic)
        """

    async def compute_ece(self) -> float:
        """Target: ECE < 0.05 (excellent calibration)"""

    async def recommend_review_threshold(self) -> float:
        """Returns optimal confidence threshold for human review."""
```

**Implementation**:
1. Track all mappings + user corrections in lineage_events
2. Compute calibration curve weekly
3. Apply calibration to future predictions
4. Surface to UI: "92% confident (based on 1,234 historical mappings)"

**Impact**:
- ✅ Users trust confidence scores
- ✅ Intelligent routing: low-confidence → human review queue
- ✅ High-confidence → auto-accepted (with audit trail)

---

#### C. Active Learning Loop

**What**: System identifies where it needs help

```python
class ActiveLearner:
    async def identify_ambiguous_labels(self) -> List[str]:
        """
        Finds labels that map to multiple canonical names with similar confidence.

        Example: "Interest" →
            - interest_expense (0.52)
            - interest_income (0.48)

        → Route to human for clarification
        → Use context (Income Statement vs Cash Flow) to disambiguate
        """

    async def prioritize_review_queue(self) -> List[Mapping]:
        """
        Smart queue ordering:
        1. High $ impact (total_assets > prepaid_expenses)
        2. Low confidence + high uncertainty
        3. Novel labels (never seen before)
        """
```

**Impact**:
- ✅ Efficient human review (work on highest-value corrections first)
- ✅ System learns from strategic corrections
- ✅ Reduces overall review burden by 70%

---

## 🎯 Priority 2: Industry-Specific Intelligence (Week 5)

### Issue
One-size-fits-all taxonomy doesn't capture industry nuances

### World-Class Solution: Multi-Industry Taxonomies

#### A. Industry Taxonomies

**Examples**:

**SaaS Companies**:
```json
{
  "canonical_name": "arr",
  "category": "income_statement",
  "display_name": "Annual Recurring Revenue",
  "aliases": ["ARR", "Recurring Revenue", "Subscription Revenue"],
  "industry": "saas",
  "derivation": "mrr * 12"
}
```

**Real Estate**:
```json
{
  "canonical_name": "noi",
  "category": "income_statement",
  "display_name": "Net Operating Income",
  "aliases": ["NOI", "Operating Income", "Net Op Income"],
  "industry": "real_estate",
  "derivation": "rental_income - operating_expenses"
}
```

**Implementation**:
```python
class IndustryTaxonomy:
    async def get_taxonomy_for_entity(
        self,
        entity_id: UUID
    ) -> List[Taxonomy]:
        """
        1. Detect industry from entity metadata or file patterns
        2. Merge base taxonomy + industry-specific items
        3. Prioritize industry-specific aliases in search
        """
```

**Impact**:
- ✅ 95%+ mapping accuracy for industry-specific metrics
- ✅ Competitive advantage (vertical expertise)

---

#### B. Smart Context Detection

**What**: Use surrounding data to improve mapping

```python
class ContextualMapper:
    def get_context(self, label: str, sheet_data: dict) -> dict:
        """
        Label: "Interest"
        Context:
        - Same sheet has "Interest Income" → likely interest_income
        - Same sheet has "Debt Balance" → likely interest_expense
        - Row above is "EBIT", row below is "EBT" → interest_expense

        Returns: enhanced confidence based on context
        """
```

**Impact**:
- ✅ Disambiguates ambiguous labels
- ✅ Fewer false positives

---

## 🎯 Priority 3: Validation & Quality Assurance (Week 6)

### Issue
System accepts nonsensical mappings

### World-Class Solution: Multi-Layer Validation

#### A. Formula-Based Validation

**What**: Detect when financials don't add up

```python
class FormulaValidator:
    DERIVATION_RULES = [
        ('gross_profit', 'revenue - cogs'),
        ('ebit', 'gross_profit - opex'),
        ('net_income', 'ebt - tax_expense'),
        ('total_assets', 'current_assets + non_current_assets'),
    ]

    async def validate_extraction(self, results: dict) -> ValidationReport:
        """
        Check:
        1. Does gross_profit = revenue - cogs? (±5% tolerance)
        2. Does balance sheet balance? (assets = liabilities + equity)
        3. Does cash flow tie out? (ending_cash = beginning_cash + net_change)

        Returns:
        - Errors (must fix)
        - Warnings (review recommended)
        - Suggestions (potential improvements)
        """
```

**User Experience**:
```
⚠️  Balance Sheet Warning:
    Total Assets ($10.2M) ≠ Liabilities + Equity ($9.8M)
    Difference: $400K (3.9%)

    Possible Issues:
    • Missing line item in liabilities?
    • Check "Deferred Revenue" mapping

    [Review Mappings] [Accept Anyway]
```

**Impact**:
- ✅ Catch 90% of mapping errors before user sees them
- ✅ Build user trust ("system caught an error I would have missed")

---

#### B. Range Validation

**What**: Flag unrealistic values

```python
class RangeValidator:
    async def check_value_ranges(
        self,
        canonical_name: str,
        value: float,
        industry: str
    ) -> ValidationResult:
        """
        gross_margin_pct: typically 0.20 - 0.80 (20-80%)
        debt_to_equity: typically 0.0 - 3.0

        If outside range:
        - Flag for review
        - Show industry benchmark
        - Suggest potential mapping error
        """
```

**Example**:
```
⚠️  Unusual Value Detected:
    Gross Margin: 127%
    Industry Benchmark (SaaS): 60-85%

    This might indicate:
    • "Gross Profit" mapped to "Revenue"?
    • Percentage already applied to dollar amount?

    [Review Mapping] [Value is Correct]
```

---

#### C. Lineage-Powered Validation (Agent 6)

**What**: Show complete provenance chain

```python
class LineageValidator:
    async def get_value_provenance(
        self,
        canonical_name: str,
        period: str
    ) -> ProvenanceChain:
        """
        Returns full audit trail:

        revenue (Q4 2023): $10.2M
        ← Mapped from: "Net Sales" (confidence: 0.95, by: claude)
        ← Extracted from: Sheet "Income Statement", Row 5
        ← Original Excel: "model_v3.xlsx", Cell B5
        ← File uploaded: 2024-01-15 by john@company.com
        ← Previous correction: None
        """
```

**User Experience**:
```
Click on any number → See full provenance
- Source cell in Excel (with screenshot)
- Mapping decision + confidence
- All transformations applied
- Historical values for comparison
```

**Impact**:
- ✅ Complete auditability (required for accounting/compliance)
- ✅ Users can verify any number in seconds
- ✅ Builds trust in system

---

## 🎯 Priority 4: User Experience Excellence (Week 7-8)

### Issue
Command-line tool; no visual feedback; hard to correct errors

### World-Class Solution: Visual Review Dashboard

#### A. Interactive Mapping Review (Agent 9 - Week 10)

**What**: Visual interface for reviewing/correcting mappings

**Key Features**:

1. **Confidence Heatmap**
```
Income Statement Mappings (15 items)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Revenue              [████████████] 95% ✓
Cost of Sales        [█████████░░░] 72% ⚠️  ← Needs Review
Gross Profit         [████████████] 93% ✓
Operating Expenses   [████░░░░░░░░] 45% ⚠️  ← Needs Review
EBITDA              [████████████] 91% ✓
```

2. **Side-by-Side Comparison**
```
Original Excel          →    Canonical Taxonomy
─────────────────────────────────────────────────
"Net Revenues"          →    revenue ✓
"COGS"                  →    cogs ✓
"SG&A Expense"          →    ??? (Unmapped) ⚠️
   Suggestions:
   • sga (0.87) [Select]
   • opex (0.65)
   • other_expense (0.23)
```

3. **Bulk Actions**
```
Select All Low Confidence (<75%) → Review Together
Apply Entity Patterns → Auto-Fix 12 items ✨
Accept All High Confidence (>90%) → Mark Complete
```

**Impact**:
- ✅ 10x faster review workflow
- ✅ Visual confidence in results
- ✅ Professional user experience

---

#### B. Excel Add-in Integration (Agent 8 - Week 9)

**What**: Users work directly in Excel with live feedback

**Features**:

1. **Live Mapping Preview** (Task Pane)
```excel
═══════════════════════════════════
DebtFund - Smart Extraction
═══════════════════════════════════
Selected Cell: B5 ("Net Revenues")

Mapped to: revenue (95% ✓)
Category: Income Statement
Period: Q4 2023
Value: $10,245,000

[View Provenance] [Change Mapping]
```

2. **Validation Warnings in Excel**
```
Excel Cell B10 has warning marker:
- Formula doesn't match:
  Expected: Gross Profit = Revenue - COGS
  Actual: $5.2M ≠ $10.2M - $4.8M ($5.4M)

[Fix in Excel] [Update Mapping]
```

3. **Smart Suggestions**
```
💡 Pattern Detected:
   You've used "Net Revenues" in Q1, Q2, Q3
   Should Q4 "Total Revenues" also map to "revenue"?

   [Yes, Apply] [No, Different]
```

**Impact**:
- ✅ Users work in familiar environment (Excel)
- ✅ Real-time feedback loop
- ✅ Reduces context switching

---

## 🎯 Priority 5: Performance & Scalability (Week 5-6)

### Issue
Database queries could be slow; no caching; inefficient for large files

### World-Class Solution: Enterprise-Grade Performance

#### A. Multi-Layer Caching

```python
class TaxonomyCache:
    """
    Layer 1: In-memory cache (milliseconds)
    Layer 2: Redis cache (5-10ms)
    Layer 3: PostgreSQL (50-100ms)
    """

    async def get_taxonomy_cached(self) -> List[Taxonomy]:
        """
        Cache key: taxonomy:v1.0.0
        TTL: 1 hour
        Invalidation: on taxonomy update

        Hit rate target: >95%
        """
```

**Impact**:
- ✅ 100x faster taxonomy lookups (1ms vs 100ms)
- ✅ Reduces database load
- ✅ Supports 1000+ concurrent extractions

---

#### B. Batch Processing

```python
class BatchProcessor:
    async def process_large_file(
        self,
        file_id: UUID,
        chunk_size: int = 1000
    ):
        """
        Split 10,000-row file into 10 chunks
        Process in parallel
        Merge results

        Time: 2 min (vs 20 min sequential)
        """
```

**Impact**:
- ✅ Handle 100K+ row models
- ✅ 10x faster processing

---

## 🎯 Priority 6: API & Integration Layer (Week 6-7)

### Issue
Taxonomy only accessible via internal module; no external integration

### World-Class Solution: RESTful Taxonomy API

```python
# Public API endpoints
@app.get("/api/v1/taxonomy")
async def get_taxonomy(
    category: Optional[str] = None,
    industry: Optional[str] = None,
    version: str = "latest"
):
    """Get taxonomy items"""

@app.get("/api/v1/taxonomy/search")
async def search_taxonomy(
    q: str,
    entity_id: Optional[UUID] = None
):
    """Search with entity-specific patterns"""

@app.post("/api/v1/taxonomy/map")
async def map_labels(
    labels: List[str],
    entity_id: Optional[UUID] = None,
    context: Optional[dict] = None
):
    """Batch mapping API"""

@app.post("/api/v1/taxonomy/correct")
async def submit_correction(
    entity_id: UUID,
    original: str,
    correct_canonical: str,
    reason: Optional[str] = None
):
    """Submit correction for learning"""
```

**Use Cases**:
- ✅ Third-party integrations
- ✅ Mobile apps
- ✅ Programmatic access for power users

---

## 🎯 Priority 7: Governance & Quality Metrics (Week 8)

### Issue
No visibility into taxonomy quality; no A/B testing

### World-Class Solution: Taxonomy Analytics

```python
class TaxonomyMetrics:
    async def compute_mapping_success_rate(self) -> float:
        """
        Success = user accepted mapping without correction
        Target: >90% for high-confidence mappings
        """

    async def compute_coverage(self) -> dict:
        """
        Coverage = % of labels successfully mapped
        Target: >95% coverage
        """

    async def identify_gaps(self) -> List[Gap]:
        """
        Frequently unmapped labels:
        - "Adjusted EBITDA" (23 occurrences, unmapped)
        → Suggest: Add to taxonomy
        """
```

**Dashboard**:
```
Taxonomy Health Report (Last 30 Days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mapping Success Rate:    87% (target: 90%) ⚠️
Coverage:                94% (target: 95%) ⚠️
Avg Confidence:          0.82 ✓
Calibration (ECE):       0.07 (target: <0.05) ⚠️

Top Gaps:
1. "Adjusted EBITDA" (23 unmapped) → [Add to Taxonomy]
2. "Non-GAAP Net Income" (18 unmapped) → [Add to Taxonomy]
3. "Platform Revenue" (15 unmapped) → [Add to Taxonomy]

Entity Pattern Learning:
- 234 patterns learned this month
- 67% reduction in corrections for repeat entities ✓
```

---

## 📊 Implementation Roadmap

### Phase 1: Foundation Complete ✅ (Current)
- ✅ 172-item base taxonomy
- ✅ Database-backed storage
- ✅ TaxonomyManager with 8 methods
- ✅ Orchestrator integration
- ✅ Test suite

### Phase 2: Intelligence Layer (Weeks 4-6)
**Priority**: CRITICAL for product differentiation

1. **Week 4**: Entity Pattern Learning
   - Implement EntityPatternManager
   - User correction workflow
   - Pattern-based suggestions

2. **Week 5**: Industry Taxonomies
   - Add 3 industry variants (SaaS, Real Estate, Manufacturing)
   - Industry detection logic
   - Context-aware mapping

3. **Week 6**: Validation & Calibration
   - Formula validation
   - Confidence calibration
   - Range checking

**Deliverables**:
- 90% mapping accuracy for repeat entities
- Intelligent review queue
- Formula-based validation catching 90% of errors

---

### Phase 3: User Experience (Weeks 7-8)

4. **Week 7**: API Layer
   - RESTful taxonomy endpoints
   - Batch mapping API
   - Correction submission API

5. **Week 8**: Analytics & Metrics
   - Taxonomy health dashboard
   - Gap analysis
   - A/B testing framework

**Deliverables**:
- Public API for integrations
- Quality metrics visibility
- Continuous improvement loop

---

### Phase 4: Polish (Weeks 9-10)

6. **Week 9**: Excel Add-in (Agent 8)
   - Task pane with live mapping
   - In-Excel validation warnings
   - Smart suggestions

7. **Week 10**: Review Dashboard (Agent 9)
   - Visual mapping review
   - Confidence heatmaps
   - Bulk correction workflows

**Deliverables**:
- Professional UI
- 10x faster review workflow
- Delightful user experience

---

## 🎯 Success Metrics: World-Class Taxonomy

| Metric | Current | Good | World-Class |
|--------|---------|------|-------------|
| **Taxonomy Coverage** | 172 items | 200+ | 500+ (multi-industry) |
| **Mapping Accuracy** | ~75% | 85% | 95% |
| **First-Pass Success** | ~60% | 75% | 90% |
| **Calibration (ECE)** | Unknown | <0.10 | <0.05 |
| **Review Time** | ~30 min/file | 15 min | 5 min |
| **Entity Learning** | No | Yes | Yes + Active Learning |
| **Validation Coverage** | 0% | 50% | 95% (formulas + ranges) |
| **User Corrections** | Manual | Tracked | Auto-Applied + Learning |
| **API Availability** | No | Basic | Enterprise-grade |
| **Multi-Industry** | No | 3 industries | 10+ industries |

---

## 💡 Quick Wins (Can Implement Now)

### 1. Add More Aliases (2 hours)
Current average: ~6 aliases/item
Target: 12+ aliases/item

**Example**:
```json
"revenue": {
  "aliases": [
    "Sales", "Net Sales", "Turnover", "Total Revenue",
    "Net Revenue", "Gross Sales", "Sales Revenue",
    "Top Line", "Income from Sales",
    // ADD:
    "Total Sales", "Revenue (Net)", "Product Revenue",
    "Service Revenue", "Operating Revenue", "Consolidated Revenue"
  ]
}
```

**Impact**: +5-10% mapping accuracy immediately

---

### 2. Add Validation Rules (4 hours)

```json
"gross_margin_pct": {
  "validation_rules": {
    "type": "percentage",
    "min_value": 0.0,
    "max_value": 1.0,
    "typical_range": [0.20, 0.80],  // ADD THIS
    "industry_benchmarks": {        // ADD THIS
      "saas": [0.65, 0.85],
      "manufacturing": [0.20, 0.40],
      "retail": [0.25, 0.45]
    }
  }
}
```

**Impact**: Catch unrealistic values, build trust

---

### 3. Entity Patterns Stub (2 hours)

```python
# Add to taxonomy.py
async def learn_from_correction(
    self,
    entity_id: UUID,
    original_label: str,
    canonical_name: str
):
    """Stub for future entity learning"""
    logger.info(f"Correction logged: {original_label} → {canonical_name}")
    # TODO: Store in entity_patterns table
    # TODO: Apply in future mappings
```

**Impact**: Foundation for learning system

---

## 🏆 Competitive Moat

**What Makes This World-Class**:

1. ✅ **Self-Improving**: Gets smarter with every upload (entity patterns + calibration)
2. ✅ **Proactive**: Catches errors before user sees them (validation + confidence)
3. ✅ **Industry-Aware**: Understands SaaS metrics ≠ Real Estate metrics
4. ✅ **Transparent**: Complete provenance chain for every number (lineage)
5. ✅ **Efficient**: Visual review in 5 min vs 30 min manual work
6. ✅ **Integrated**: Works in Excel where users already are
7. ✅ **Trustworthy**: Calibrated confidence scores + validation

**The "Wow" Moment**:
```
Upload #1: User corrects 15 mappings, takes 30 min
Upload #2: System auto-applies corrections, user reviews in 5 min
Upload #3: 95% perfect, user just verifies outliers

User thinks: "This system actually learns from me. It's like having
             a smart junior analyst who remembers everything."
```

---

## 🎯 Recommended Next Steps

### Immediate (This Week):
1. ✅ Add more aliases to existing taxonomy (+10% accuracy)
2. ✅ Add validation rules with benchmarks
3. ✅ Create entity_patterns integration stub

### Next Sprint (Week 4):
1. Implement EntityPatternManager
2. Build user correction workflow
3. Add 3 industry taxonomy variants

### Following Sprint (Week 5-6):
1. Confidence calibration system
2. Formula-based validation
3. Taxonomy API endpoints

Would you like me to:
1. **Implement Quick Wins** (aliases, validation rules) right now?
2. **Design EntityPatternManager** in detail for Week 4?
3. **Create Industry Taxonomies** (SaaS, Real Estate, Manufacturing)?
4. **Build Validation Framework** with formula checking?

What resonates most for creating that world-class experience?
