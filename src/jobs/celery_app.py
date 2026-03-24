"""
Celery application configuration for TabIntelligence extraction pipeline.

Includes:
- Dead Letter Queue (DLQ) for failed tasks
- Automatic retry with exponential backoff
- Queue routing configuration
"""

from celery import Celery
from kombu import Exchange, Queue

from src.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tabintelligence", broker=settings.redis_url, backend=settings.redis_url, include=["src.jobs.tasks"]
)

# Define exchanges
default_exchange = Exchange("tabintelligence", type="direct", durable=True)
dlq_exchange = Exchange("tabintelligence.dlq", type="direct", durable=True)

# Define queues
celery_app.conf.task_queues = (
    Queue("extraction", exchange=default_exchange, routing_key="extraction.default", durable=True),
    Queue("extraction.dlq", exchange=dlq_exchange, routing_key="extraction.failed", durable=True),
)

# Default queue for tasks
celery_app.conf.task_default_queue = "extraction"
celery_app.conf.task_default_exchange = "tabintelligence"
celery_app.conf.task_default_routing_key = "extraction.default"

celery_app.conf.update(
    # Serialization — prefer JSON; accept pickle for local dev (file_bytes fallback)
    task_serializer="pickle",
    accept_content=["json", "pickle"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Requeue if worker crashes
    worker_prefetch_multiplier=1,  # Take one task at a time (for long tasks)
    worker_max_tasks_per_child=50,  # Recycle worker after 50 tasks
    # Time limits (match extraction timeout in config)
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
    # Result backend
    result_expires=3600,  # Keep results for 1 hour
    # Retry defaults (individual tasks override via decorator)
    task_retry_backoff=True,  # Exponential backoff
    task_retry_backoff_max=600,  # 10 minutes max
    task_retry_jitter=True,  # Add jitter to prevent thundering herd
)
