"""Exception classes for NPS API."""


class NPSError(Exception):
    """Base exception for NPS API errors."""

    pass


class NPSAuthError(NPSError):
    """Authentication error."""

    pass


class NPSAPIError(NPSError):
    """API request error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
