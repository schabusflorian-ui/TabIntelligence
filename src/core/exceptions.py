"""
Custom exception hierarchy for DebtFund.

All DebtFund exceptions inherit from DebtFundError for easy catching.
"""


class DebtFundError(Exception):
    """Base exception for all DebtFund errors."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(DebtFundError):
    """Configuration or environment setup issues."""

    def __init__(self, message: str, missing_vars: list = None):
        details = {"missing_vars": missing_vars} if missing_vars else {}
        super().__init__(message, details)


class ExtractionError(DebtFundError):
    """Base exception for extraction pipeline errors."""

    def __init__(self, message: str, stage: str = None, file_id: str = None):
        details = {}
        if stage:
            details["stage"] = stage
        if file_id:
            details["file_id"] = file_id
        super().__init__(message, details)


class ClaudeAPIError(ExtractionError):
    """
    Claude API failures (rate limits, network, invalid response).

    Attributes:
        stage: Which extraction stage failed (e.g., "parsing", "triage")
        retry_count: Number of retries attempted
        status_code: HTTP status code if available
    """

    def __init__(
        self,
        message: str,
        stage: str,
        retry_count: int = 0,
        status_code: int = None,
        file_id: str = None,
    ):
        self.stage = stage
        self.retry_count = retry_count
        self.status_code = status_code

        details = {
            "stage": stage,
            "retry_count": retry_count,
        }
        if status_code:
            details["status_code"] = status_code

        super().__init__(
            f"[{stage}] {message} (retries: {retry_count})",
            stage=stage,
            file_id=file_id,
        )


class ValidationError(ExtractionError):
    """Validation failures (Stage 4)."""

    def __init__(self, message: str, validation_type: str = None, file_id: str = None):
        details = {}
        if validation_type:
            details["validation_type"] = validation_type
        super().__init__(message, stage="validation", file_id=file_id)
        self.details.update(details)


class LineageError(DebtFundError):
    """Lineage system errors."""

    def __init__(self, message: str, job_id: str = None):
        details = {}
        if job_id:
            details["job_id"] = job_id
        super().__init__(message, details)


class LineageIncompleteError(LineageError):
    """
    Lineage completeness check failed - EXISTENTIAL error.

    Without complete lineage, there is no trust. Without trust, there is no product.

    Attributes:
        missing_events: List of stages that didn't emit lineage events
        job_id: ID of the job with incomplete lineage
    """

    def __init__(self, missing_events: list, job_id: str = None):
        self.missing_events = missing_events
        message = f"Lineage incomplete: {len(missing_events)} missing events (stages: {missing_events})"
        super().__init__(message, job_id=job_id)
        self.details["missing_events"] = missing_events


class DatabaseError(DebtFundError):
    """Database operation failures."""

    def __init__(self, message: str, operation: str = None, table: str = None):
        details = {}
        if operation:
            details["operation"] = operation
        if table:
            details["table"] = table
        super().__init__(message, details)


class FileStorageError(DebtFundError):
    """S3/MinIO storage operation failures."""

    def __init__(self, message: str, bucket: str = None, key: str = None):
        details = {}
        if bucket:
            details["bucket"] = bucket
        if key:
            details["key"] = key
        super().__init__(message, details)


class AuthenticationError(DebtFundError):
    """Authentication/authorization failures."""

    def __init__(self, message: str, user_id: str = None):
        details = {}
        if user_id:
            details["user_id"] = user_id
        super().__init__(message, details)


class RateLimitError(ClaudeAPIError):
    """
    Rate limit exceeded for external API (Claude, etc.).

    This is a specific case of ClaudeAPIError for retry handling.
    """

    def __init__(self, message: str, stage: str, retry_after: int = None):
        super().__init__(message, stage=stage, status_code=429)
        if retry_after:
            self.details["retry_after"] = retry_after


class InvalidFileError(DebtFundError):
    """Invalid or corrupted file uploaded."""

    def __init__(self, message: str, filename: str = None, file_type: str = None):
        details = {}
        if filename:
            details["filename"] = filename
        if file_type:
            details["file_type"] = file_type
        super().__init__(message, details)


class DuplicateFileError(DebtFundError):
    """File with identical content already uploaded."""

    def __init__(self, message: str, content_hash: str = None, existing_file_id: str = None):
        details = {}
        if content_hash:
            details["content_hash"] = content_hash
        if existing_file_id:
            details["existing_file_id"] = existing_file_id
        super().__init__(message, details)
