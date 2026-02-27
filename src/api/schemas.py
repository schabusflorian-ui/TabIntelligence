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
