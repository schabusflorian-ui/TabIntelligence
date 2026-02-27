"""
Pydantic response models for all API endpoints.

These models provide:
- Typed OpenAPI documentation
- Response validation
- Consistent serialization
"""
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime


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
    """Full circuit breaker stats returned by /health/health/circuit-breaker."""
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
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


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

class HierarchyChild(BaseModel):
    canonical_name: str
    display_name: Optional[str] = None

class HierarchyNode(BaseModel):
    canonical_name: str
    display_name: Optional[str] = None
    category: str
    children: List[HierarchyChild]


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

class EntityResponse(BaseModel):
    id: str
    name: str
    industry: Optional[str] = None
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
# Job Retry
# ============================================================================

class RetryResponse(BaseModel):
    original_job_id: str
    new_job_id: str
    task_id: Optional[str] = None
    status: str
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
