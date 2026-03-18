"""
Pydantic response models for all API endpoints.

These models provide:
- Typed OpenAPI documentation
- Response validation
- Consistent serialization
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ============================================================================
# Root / Service Info
# ============================================================================


class ServiceInfoResponse(BaseModel):
    service: str
    version: str
    status: str


# ============================================================================
# Health Check (GET /health)
# ============================================================================


class ComponentStatus(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    bucket: Optional[str] = None
    error: Optional[str] = None


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    components: Dict[str, ComponentStatus]


# ============================================================================
# Health Probes (health router)
# ============================================================================


class LivenessResponse(BaseModel):
    status: str
    timestamp: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    query_time_ms: Optional[float] = None
    error: Optional[str] = None
    timestamp: str


class PoolInfo(BaseModel):
    size: int
    checked_out: int
    overflow: int
    total_connections: int


class CircuitBreakerInfo(BaseModel):
    state: str
    success_rate: float
    total_requests: int
    failed_requests: int


class DatabaseHealthResponse(BaseModel):
    status: str
    query_time_ms: Optional[float] = None
    pool: Optional[PoolInfo] = None
    circuit_breaker: Optional[CircuitBreakerInfo] = None
    postgresql_version: Optional[str] = None
    timestamp: str
    warnings: Optional[List[str]] = None
    error: Optional[str] = None


class CircuitBreakerStatusResponse(BaseModel):
    """Full circuit breaker stats returned by /health/circuit-breaker."""

    state: str
    timestamp: str
    model_config = {"extra": "allow"}


# ============================================================================
# File Upload
# ============================================================================


class FileUploadResponse(BaseModel):
    file_id: str
    job_id: Optional[str] = None
    s3_key: Optional[str] = None
    task_id: Optional[str] = None
    status: str
    message: str
    original_upload: Optional[str] = None


# ============================================================================
# Job Status
# ============================================================================


class JobStatusResponse(BaseModel):
    job_id: str
    file_id: str
    status: str
    current_stage: Optional[str] = None
    progress_percent: Optional[int] = None
    stages_completed: Optional[int] = None  # 0-5
    total_stages: int = 5
    result: Optional[Dict[str, Any]] = None
    quality: Optional[Dict[str, Any]] = None
    model_type: Optional[str] = None
    error: Optional[str] = None
    filename: Optional[str] = None
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    quality_grade: Optional[str] = None


# ============================================================================
# Export
# ============================================================================


class ExportFilters(BaseModel):
    min_confidence: Optional[float] = None
    canonical_name: Optional[str] = None
    sheet: Optional[str] = None


class ExportResponse(BaseModel):
    job_id: str
    file_id: str
    sheets: List[str] = []
    line_items: List[Dict[str, Any]] = []
    line_items_count: int
    tokens_used: int = 0
    cost_usd: float = 0.0
    validation: Optional[Dict[str, Any]] = None
    quality: Optional[Dict[str, Any]] = None
    model_type: Optional[str] = None
    validation_delta: Optional[Dict[str, Any]] = None
    filters_applied: ExportFilters


# ============================================================================
# Taxonomy
# ============================================================================


class TaxonomyStatsResponse(BaseModel):
    total_items: int
    categories: Dict[str, int]


class TaxonomyItemResponse(BaseModel):
    canonical_name: str
    category: str
    display_name: Optional[str] = None
    aliases: List[str] = []
    definition: Optional[str] = None
    typical_sign: Optional[str] = None
    parent_canonical: Optional[str] = None
    validation_rules: Optional[Dict[str, Any]] = None
    deprecated: bool = False
    deprecated_redirect: Optional[str] = None
    deprecated_at: Optional[str] = None


class TaxonomyListResponse(BaseModel):
    count: int
    items: List[TaxonomyItemResponse]


class TaxonomySearchItem(BaseModel):
    canonical_name: str
    category: str
    display_name: Optional[str] = None
    aliases: List[str] = []
    definition: Optional[str] = None
    typical_sign: Optional[str] = None


class TaxonomySearchResponse(BaseModel):
    query: str
    count: int
    items: List[TaxonomySearchItem]


class HierarchyNode(BaseModel):
    canonical_name: str
    display_name: Optional[str] = None
    category: str
    typical_sign: Optional[str] = None
    children: List["HierarchyNode"] = []


HierarchyNode.model_rebuild()


# ============================================================================
# Job Listing
# ============================================================================


class JobListItem(BaseModel):
    job_id: str
    file_id: str
    status: str
    current_stage: Optional[str] = None
    progress_percent: Optional[int] = None
    error: Optional[str] = None
    filename: Optional[str] = None
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobListResponse(BaseModel):
    count: int
    limit: int
    offset: int
    jobs: List[JobListItem]


# ============================================================================
# Entity CRUD
# ============================================================================


class EntityCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    fiscal_year_end: Optional[int] = Field(None, ge=1, le=12, description="Fiscal year end month (1-12)")
    default_currency: Optional[str] = Field(
        None, min_length=3, max_length=3, description="ISO 4217 currency code"
    )
    reporting_standard: Optional[str] = Field(None, max_length=20, description="GAAP, IFRS, etc.")


class UpdateEntityRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    fiscal_year_end: Optional[int] = Field(None, ge=1, le=12)
    default_currency: Optional[str] = Field(None, min_length=3, max_length=3)
    reporting_standard: Optional[str] = Field(None, max_length=20)


class EntityResponse(BaseModel):
    id: str
    name: str
    industry: Optional[str] = None
    fiscal_year_end: Optional[int] = None
    default_currency: Optional[str] = None
    reporting_standard: Optional[str] = None
    created_at: Optional[str] = None


class EntityListResponse(BaseModel):
    count: int
    entities: List[EntityResponse]


class EntityDetailResponse(EntityResponse):
    patterns_count: int = 0
    files_count: int = 0


# ============================================================================
# Lineage
# ============================================================================


class LineageEventItem(BaseModel):
    event_id: str
    stage_name: str
    timestamp: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class LineageResponse(BaseModel):
    job_id: str
    status: str
    events_count: int
    events: List[LineageEventItem]


# ============================================================================
# Extraction Diff
# ============================================================================


class DiffItemResponse(BaseModel):
    canonical_name: str
    change_type: str
    details: Dict[str, Any] = {}


class ExtractionDiffResponse(BaseModel):
    job_a_id: str
    job_b_id: str
    summary: Dict[str, int]
    added_items: List[DiffItemResponse] = []
    removed_items: List[DiffItemResponse] = []
    changed_items: List[DiffItemResponse] = []
    value_changes: List[Dict[str, Any]] = []
    warnings: List[str] = []
    metadata: Dict[str, Any] = {}


# ============================================================================
# Item-Level Lineage
# ============================================================================


class ItemTransformation(BaseModel):
    stage: str
    action: str
    original_label: str
    timestamp: Optional[str] = None
    model_config = {"extra": "allow"}


class ItemLineageResponse(BaseModel):
    job_id: str
    canonical_name: str
    transformations: List[ItemTransformation]


# ============================================================================
# Job Retry
# ============================================================================


class RetryResponse(BaseModel):
    original_job_id: str
    new_job_id: str
    task_id: Optional[str] = None
    status: str
    message: str


# ============================================================================
# Job Review
# ============================================================================


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    reason: Optional[str] = Field(None, max_length=1000)


class ReviewDecisionResponse(BaseModel):
    job_id: str
    previous_status: str
    new_status: str
    decision: str
    reason: Optional[str] = None
    message: str


# ============================================================================
# DLQ Admin
# ============================================================================


class DLQEntryListItem(BaseModel):
    dlq_id: str
    task_id: str
    task_name: str
    error: str
    replayed: int
    replayed_at: Optional[str] = None
    created_at: Optional[str] = None


class DLQEntryListResponse(BaseModel):
    count: int
    entries: List[DLQEntryListItem]


class DLQEntryDetailResponse(DLQEntryListItem):
    task_args: Optional[Any] = None
    task_kwargs: Optional[Any] = None
    traceback: Optional[str] = None
    replayed_task_id: Optional[str] = None


# ============================================================================
# User Corrections & Entity Patterns
# ============================================================================


class CorrectionItem(BaseModel):
    original_label: str
    canonical_name: str
    sheet: Optional[str] = None  # optional context


class CorrectionRequest(BaseModel):
    corrections: List[CorrectionItem]


class CorrectionResponse(BaseModel):
    patterns_created: int
    patterns_updated: int
    message: str


# ============================================================================
# Corrections Application (WS-J: retroactive apply, preview, undo, bulk)
# ============================================================================


class ApplyCorrectionItem(BaseModel):
    original_label: str
    new_canonical_name: str
    sheet: Optional[str] = None  # disambiguate when same label on multiple sheets


class ApplyCorrectionRequest(BaseModel):
    corrections: List[ApplyCorrectionItem] = Field(..., min_length=1, max_length=100)


class CorrectionDiff(BaseModel):
    original_label: str
    sheet: Optional[str] = None
    row: Optional[int] = None
    old_canonical_name: str
    new_canonical_name: str
    old_confidence: float
    new_confidence: float = 1.0


class ApplyCorrectionResponse(BaseModel):
    job_id: str
    corrections_applied: int
    patterns_created: int
    patterns_updated: int
    facts_updated: int
    diffs: List[CorrectionDiff]
    message: str


class PreviewCorrectionResponse(BaseModel):
    job_id: str
    corrections_count: int
    diffs: List[CorrectionDiff]
    warnings: List[str] = []
    message: str


class CorrectionHistoryItem(BaseModel):
    id: str
    job_id: str
    original_label: str
    sheet: Optional[str] = None
    old_canonical_name: str
    new_canonical_name: str
    old_confidence: float
    new_confidence: float
    reverted: bool
    reverted_at: Optional[str] = None
    created_at: Optional[str] = None


class CorrectionHistoryResponse(BaseModel):
    job_id: str
    corrections: List[CorrectionHistoryItem]
    total: int
    offset: int = 0
    limit: int = 100


class UndoCorrectionResponse(BaseModel):
    correction_id: str
    job_id: str
    original_label: str
    restored_canonical_name: str
    message: str


class PatternResponse(BaseModel):
    id: str
    original_label: str
    canonical_name: str
    confidence: float
    occurrence_count: int
    created_by: str
    created_at: Optional[str] = None


class PatternListResponse(BaseModel):
    entity_id: str
    patterns: List[PatternResponse]
    total_patterns: int


# ============================================================================
# Pattern Stats (GET /api/v1/entities/{entity_id}/pattern-stats)
# ============================================================================


class PatternStatsResponse(BaseModel):
    entity_id: str
    total_patterns: int
    active_patterns: int
    avg_confidence: float
    by_method: Dict[str, int]
    tokens_saved_estimate: int
    cost_saved_estimate: float
    top_patterns: List[PatternResponse]
    conflicted_patterns: List[PatternResponse]


# ============================================================================
# Learned Aliases
# ============================================================================


class LearnedAliasResponse(BaseModel):
    id: str
    canonical_name: str
    alias_text: str
    occurrence_count: int
    source_entities: List[str]
    promoted: bool
    created_at: Optional[str] = None


class LearnedAliasListResponse(BaseModel):
    aliases: List[LearnedAliasResponse]
    total: int


class LearnedAliasPromoteResponse(BaseModel):
    id: str
    canonical_name: str
    alias_text: str
    promoted: bool
    message: str


# ============================================================================
# Extraction Facts (GET /api/v1/facts)
# ============================================================================


class ExtractionFactResponse(BaseModel):
    id: str
    job_id: str
    entity_id: Optional[str] = None
    canonical_name: str
    original_label: Optional[str] = None
    period: str
    period_normalized: Optional[str] = None
    value: float
    confidence: Optional[float] = None
    sheet_name: Optional[str] = None
    row_index: Optional[int] = None
    mapping_method: Optional[str] = None
    taxonomy_category: Optional[str] = None
    validation_passed: Optional[bool] = None
    currency_code: Optional[str] = None
    source_unit: Optional[str] = None
    source_scale: Optional[float] = None
    created_at: Optional[str] = None


class FactsListResponse(BaseModel):
    facts: List[ExtractionFactResponse]
    count: int
    limit: int
    offset: int


# ============================================================================
# Analytics: Entity Financials
# ============================================================================


class PeriodValue(BaseModel):
    period: str
    amount: float


class FinancialLineItem(BaseModel):
    canonical_name: str
    taxonomy_category: Optional[str] = None
    values: List[PeriodValue]


class EntityFinancialsResponse(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    items: List[FinancialLineItem]
    periods: List[str] = []
    source: str = "facts"
    total_items: Optional[int] = None


# ============================================================================
# Analytics: Cross-Entity Comparison
# ============================================================================


class EntityComparisonValue(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    amount: Optional[float] = None
    confidence: Optional[float] = None
    period_raw: Optional[str] = None
    period_normalized: Optional[str] = None
    currency_code: Optional[str] = None
    source_unit: Optional[str] = None
    fiscal_year_end: Optional[int] = None
    original_amount: Optional[float] = None
    converted_amount: Optional[float] = None
    fx_rate_used: Optional[float] = None


class ComparisonItem(BaseModel):
    canonical_name: str
    period: Optional[str] = None
    entities: List[EntityComparisonValue]
    alignment_warnings: List[str] = []


class CrossEntityComparisonResponse(BaseModel):
    canonical_names: List[str]
    period: Optional[str] = None
    period_normalized: Optional[str] = None
    year: Optional[int] = None
    comparisons: List[ComparisonItem]
    normalization_notes: List[str] = []


# ============================================================================
# Analytics: Portfolio Summary
# ============================================================================


class QualityDistribution(BaseModel):
    grade: str
    count: int


class PortfolioSummaryResponse(BaseModel):
    total_entities: int
    total_jobs: int
    total_facts: int
    avg_confidence: Optional[float] = None
    quality_distribution: List[QualityDistribution] = []
    period: Optional[str] = None


# ============================================================================
# Analytics: Entity Trends
# ============================================================================


class TrendPoint(BaseModel):
    period: str
    amount: float
    yoy_change_pct: Optional[float] = None


class EntityTrendsResponse(BaseModel):
    entity_id: str
    canonical_name: str
    trend: List[TrendPoint]


# ============================================================================
# Analytics: Taxonomy Coverage
# ============================================================================


class TaxonomyCoverageItem(BaseModel):
    canonical_name: str
    category: str
    times_mapped: int
    avg_confidence: Optional[float] = None


class TaxonomyCoverageResponse(BaseModel):
    total_taxonomy_items: int
    items_ever_mapped: int
    coverage_pct: float
    most_common: List[TaxonomyCoverageItem] = []
    never_mapped: List[str] = []


# ============================================================================
# Analytics: Cost Analytics
# ============================================================================


class CostByEntity(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    total_cost: float
    job_count: int


class DailyCost(BaseModel):
    date: str
    cost: float
    job_count: int


class CostAnalyticsResponse(BaseModel):
    total_cost: float
    total_jobs: int
    avg_cost_per_job: float
    cost_by_entity: List[CostByEntity] = []
    cost_trend_daily: List[DailyCost] = []


# ============================================================================
# Analytics: Structured Statement (Phase 7 — Comparison)
# ============================================================================


class StatementLineItem(BaseModel):
    canonical_name: str
    display_name: Optional[str] = None
    hierarchy_level: int = 0
    is_subtotal: bool = False
    parent_canonical: Optional[str] = None
    values: Dict[str, float] = {}  # period -> amount
    children: List["StatementLineItem"] = []

    model_config = {"from_attributes": True}


StatementLineItem.model_rebuild()


class StructuredStatementResponse(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    category: str
    periods: List[str] = []
    items: List[StatementLineItem]
    total_items: int = 0


# ============================================================================
# Analytics: Multi-Period Comparison (Phase 7 — Comparison)
# ============================================================================


class PeriodComparisonValue(BaseModel):
    period: str
    value: Optional[float] = None


class PeriodDelta(BaseModel):
    from_period: str
    to_period: str
    absolute_change: Optional[float] = None
    pct_change: Optional[float] = None


class ComparisonLineItem(BaseModel):
    canonical_name: str
    display_name: Optional[str] = None
    taxonomy_category: Optional[str] = None
    values: List[PeriodComparisonValue]
    deltas: List[PeriodDelta] = []


class MultiPeriodComparisonResponse(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    canonical_names: List[str]
    periods: List[str]
    items: List[ComparisonLineItem]


# ============================================================================
# Intelligence Layer: Confidence Calibration
# ============================================================================


class CalibrationBucket(BaseModel):
    bin_start: float
    bin_end: float
    total_predictions: int
    correct_predictions: int
    accuracy: Optional[float] = None


class ConfidenceCalibrationResponse(BaseModel):
    buckets: List[CalibrationBucket]
    total_facts: int
    total_corrections: int


# ============================================================================
# Intelligence Layer: Review Suggestions
# ============================================================================


class ReviewSuggestionItem(BaseModel):
    original_label: str
    canonical_name: str
    sheet: Optional[str] = None
    confidence: float
    priority_score: int
    reasons: List[str]


class ReviewSuggestionsResponse(BaseModel):
    job_id: str
    suggestions: List[ReviewSuggestionItem]
    total_items: int


# ============================================================================
# Analytics: Unmapped Labels
# ============================================================================


class UnmappedLabelItem(BaseModel):
    label_normalized: str
    original_variants: List[str]
    total_occurrences: int
    entity_count: int
    entity_ids: List[str]
    sheet_names: List[str]
    taxonomy_category_hint: Optional[str] = None


class UnmappedLabelAggregationResponse(BaseModel):
    labels: List[UnmappedLabelItem]
    total: int
    limit: int
    offset: int


# ============================================================================
# Analytics: Anomaly Detection
# ============================================================================


class AnomalyItem(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    canonical_name: str
    period: str
    value: float
    is_outlier: bool
    z_score: Optional[float] = None
    iqr_distance: Optional[float] = None
    direction: Optional[str] = None


class AnomalySummary(BaseModel):
    canonical_name: str
    period: str
    peer_count: int
    peer_mean: float
    peer_median: float
    outlier_count: int
    items: List[AnomalyItem]


class AnomalyDetectionResponse(BaseModel):
    method: str
    threshold: float
    summaries: List[AnomalySummary]
    total_outliers: int
    total_items: int


# ============================================================================
# Analytics: Taxonomy Gap Suggestions
# ============================================================================


class MappingSuggestion(BaseModel):
    canonical_name: str
    confidence: float
    reason: str
    source: str  # "entity_pattern", "taxonomy_alias", "learned_alias"


class SuggestionResponse(BaseModel):
    label: str
    suggestions: List[MappingSuggestion]


class AcceptSuggestionRequest(BaseModel):
    canonical_name: str
    entity_id: Optional[str] = None


class AcceptSuggestionResponse(BaseModel):
    label: str
    canonical_name: str
    pattern_created: bool
    alias_created: bool


# ============================================================================
# Analytics: Quality Trending
# ============================================================================


class QualitySnapshotItem(BaseModel):
    snapshot_date: str
    avg_confidence: float
    quality_grade: str
    total_facts: int
    total_jobs: int
    unmapped_label_count: int


class QualityTrendResponse(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    snapshots: List[QualitySnapshotItem]


# ============================================================================
# Taxonomy Governance (Deprecation & Changelog)
# ============================================================================


class DeprecateRequest(BaseModel):
    redirect_to: Optional[str] = None


class DeprecateResponse(BaseModel):
    canonical_name: str
    deprecated: bool
    deprecated_redirect: Optional[str] = None
    deprecated_at: Optional[str] = None


class ChangelogEntry(BaseModel):
    id: str
    canonical_name: str
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: str
    taxonomy_version: Optional[str] = None
    created_at: str


class ChangelogResponse(BaseModel):
    count: int
    entries: List[ChangelogEntry]
