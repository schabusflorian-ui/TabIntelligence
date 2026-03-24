"""
Distributed tracing configuration using OpenTelemetry.

Provides end-to-end request tracing across:
- FastAPI endpoints
- Celery tasks
- Database queries
- Redis operations
"""

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(service_name: str = "tabintelligence-api"):
    """
    Initialize distributed tracing.

    Call this once during application startup.

    Args:
        service_name: Name of the service for trace identification

    Returns:
        TracerProvider instance
    """
    # Create tracer provider with service metadata
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    # Configure Jaeger exporter
    # Use environment variable for flexibility (defaults to localhost for local dev)
    import os

    jaeger_host = os.getenv("JAEGER_AGENT_HOST", "localhost")
    jaeger_exporter = JaegerExporter(
        agent_host_name=jaeger_host,
        agent_port=6831,
    )

    # Add span processor
    provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

    # Set as global tracer
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries
    CeleryInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()

    return provider


def instrument_fastapi(app):
    """
    Instrument FastAPI application with distributed tracing.

    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor().instrument_app(app)


def get_current_trace_id() -> str:
    """
    Get trace ID for current request (useful for logging correlation).

    Returns:
        32-character hex trace ID, or "no-trace" if not in a trace context
    """
    span = trace.get_current_span()
    if span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return "no-trace"
