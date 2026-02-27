"""
Request ID middleware for correlation tracking.

Generates a unique request ID for each incoming request and:
1. Adds it to the request context (accessible to loggers)
2. Returns it in response headers (X-Request-ID)
3. Accepts existing request IDs from clients

This enables end-to-end request correlation across logs and traces.
"""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import request_id_ctx


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Add unique request ID to all requests for correlation.

    The request ID is:
    - Generated as UUID v4 if not provided by client
    - Extracted from X-Request-ID header if provided
    - Added to response headers
    - Set in context for logger access
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and add request ID.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            Response with X-Request-ID header
        """
        # Generate or extract request ID
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())

        # Set in context (available to all loggers in this request)
        request_id_ctx.set(request_id)

        # Process request
        response = await call_next(request)

        # Add to response headers for client tracking
        response.headers['X-Request-ID'] = request_id

        return response
