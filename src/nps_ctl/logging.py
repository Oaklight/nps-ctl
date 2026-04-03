"""Enhanced logging module for NPS API operations.

This module provides structured logging for NPSClient and NPSCluster operations,
including connection attempts, request/response tracking, and operation results.

It also provides FlushingConsole for immediate output visibility through proxies.

Usage:
    >>> from nps_ctl.logging import configure_logging, get_logger
    >>> configure_logging(level="DEBUG")
    >>> logger = get_logger("nps_ctl.base")
"""

import logging
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any

from rich.console import Console

# Custom log level NOTICE (25) - between INFO (20) and WARNING (30)
# Used for key phase information that should be visible by default
NOTICE = 25
logging.addLevelName(NOTICE, "NOTICE")


def _notice(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log a message at NOTICE level."""
    if self.isEnabledFor(NOTICE):
        self._log(NOTICE, message, args, **kwargs)


# Add notice method to Logger class
logging.Logger.notice = _notice  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]


class LogLevel(Enum):
    """Log level enumeration."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    NOTICE = NOTICE
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


@dataclass
class OperationContext:
    """Context for logging an operation.

    Attributes:
        operation: Name of the operation (e.g., "add_client", "sync_from").
        target: Target of the operation (e.g., server URL, edge name).
        details: Additional details about the operation.
    """

    operation: str
    target: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        """Format context as a log-friendly string."""
        base = f"[{self.operation}] -> {self.target}"
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{base} ({detail_str})"
        return base


class NPSLogFormatter(logging.Formatter):
    """Custom formatter for NPS operations with colored output.

    Provides structured log output with timestamps, log levels, and
    operation context for better debugging and monitoring.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "NOTICE": "\033[34m",  # Blue - for key phase info
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",
    }

    def __init__(self, use_colors: bool = True) -> None:
        """Initialize the formatter.

        Args:
            use_colors: Whether to use ANSI colors in output.
        """
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.use_colors = use_colors and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with optional colors.

        Args:
            record: The log record to format.

        Returns:
            Formatted log string.
        """
        if self.use_colors:
            color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
            reset = self.COLORS["RESET"]
            record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


class OperationLogger:
    """Helper class for logging operations with context.

    Provides methods for logging connection attempts, request/response cycles,
    and operation results with consistent formatting.
    """

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize the operation logger.

        Args:
            logger: The underlying Python logger instance.
        """
        self._logger = logger

    def connection_attempt(self, url: str, **kwargs: Any) -> None:
        """Log a connection attempt.

        Args:
            url: The URL being connected to.
            **kwargs: Additional connection parameters.
        """
        details = ", ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
        msg = f"Connecting to {url}"
        if details:
            msg += f" ({details})"
        self._logger.info(msg)

    def connection_success(
        self, url: str, response_time_ms: float | None = None
    ) -> None:
        """Log a successful connection.

        Args:
            url: The URL that was connected to.
            response_time_ms: Response time in milliseconds.
        """
        msg = f"Connected to {url}"
        if response_time_ms is not None:
            msg += f" ({response_time_ms:.1f}ms)"
        self._logger.debug(msg)

    def connection_failed(
        self, url: str, error: str | Exception, attempt: int | None = None
    ) -> None:
        """Log a failed connection attempt.

        Args:
            url: The URL that failed to connect.
            error: The error message or exception.
            attempt: The attempt number (for retries).
        """
        msg = f"Connection failed to {url}: {error}"
        if attempt is not None:
            msg = f"[Attempt {attempt}] {msg}"
        self._logger.warning(msg)

    def request_start(
        self, method: str, endpoint: str, data: dict[str, Any] | None = None
    ) -> None:
        """Log the start of an API request.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint.
            data: Request data (sensitive fields will be masked).
        """
        msg = f"Request: {method} {endpoint}"
        if data:
            # Mask sensitive fields
            safe_data = _mask_sensitive_data(data)
            msg += f" | data={safe_data}"
        self._logger.info(msg)

    def request_success(
        self,
        method: str,
        endpoint: str,
        status: int | str | None = None,
        response_time_ms: float | None = None,
    ) -> None:
        """Log a successful API request.

        Args:
            method: HTTP method.
            endpoint: API endpoint.
            status: Response status code or API status.
            response_time_ms: Response time in milliseconds.
        """
        msg = f"Response: {method} {endpoint}"
        if status is not None:
            msg += f" | status={status}"
        if response_time_ms is not None:
            msg += f" | {response_time_ms:.1f}ms"
        self._logger.info(msg)

    def request_failed(
        self,
        method: str,
        endpoint: str,
        error: str | Exception,
        status_code: int | None = None,
    ) -> None:
        """Log a failed API request.

        Args:
            method: HTTP method.
            endpoint: API endpoint.
            error: The error message or exception.
            status_code: HTTP status code if available.
        """
        msg = f"Request failed: {method} {endpoint}"
        if status_code is not None:
            msg += f" | HTTP {status_code}"
        msg += f" | {error}"
        self._logger.error(msg)

    def operation_start(self, ctx: OperationContext) -> None:
        """Log the start of an operation.

        This logs at NOTICE level so it's visible by default.

        Args:
            ctx: Operation context.
        """
        self._logger.log(NOTICE, f"Starting {ctx}")

    def operation_success(
        self,
        ctx: OperationContext,
        result: Any = None,
        duration_ms: float | None = None,
    ) -> None:
        """Log a successful operation.

        This logs at NOTICE level so it's visible by default.

        Args:
            ctx: Operation context.
            result: Operation result (optional).
            duration_ms: Operation duration in milliseconds.
        """
        msg = f"Completed {ctx}"
        if result is not None:
            msg += f" | result={result}"
        if duration_ms is not None:
            msg += f" | {duration_ms:.1f}ms"
        self._logger.log(NOTICE, msg)

    def operation_failed(
        self,
        ctx: OperationContext,
        error: str | Exception,
        duration_ms: float | None = None,
    ) -> None:
        """Log a failed operation.

        Args:
            ctx: Operation context.
            error: The error message or exception.
            duration_ms: Operation duration in milliseconds.
        """
        msg = f"Failed {ctx} | {error}"
        if duration_ms is not None:
            msg += f" | {duration_ms:.1f}ms"
        self._logger.error(msg)

    def sync_progress(
        self,
        source: str,
        target: str,
        item_type: str,
        item_name: str,
        success: bool,
    ) -> None:
        """Log sync progress for cluster operations.

        Args:
            source: Source edge name.
            target: Target edge name.
            item_type: Type of item being synced (client, tunnel, host).
            item_name: Name of the item.
            success: Whether the sync was successful.
        """
        status = "✓" if success else "✗"
        msg = f"Sync {source} -> {target} | {item_type}:{item_name} | {status}"
        if success:
            self._logger.info(msg)
        else:
            self._logger.warning(msg)

    def cluster_operation(
        self,
        operation: str,
        edge_name: str,
        success: bool,
        details: str | None = None,
    ) -> None:
        """Log a cluster-wide operation result.

        Args:
            operation: Operation name.
            edge_name: Edge name.
            success: Whether the operation was successful.
            details: Additional details.
        """
        status = "success" if success else "failed"
        msg = f"Cluster {operation} on {edge_name}: {status}"
        if details:
            msg += f" | {details}"
        if success:
            self._logger.debug(msg)
        else:
            self._logger.error(msg)

    def phase_info(self, message: str) -> None:
        """Log a phase/milestone message at NOTICE level.

        Use this for key phase transitions that should be visible by default.

        Args:
            message: The phase message.
        """
        self._logger.log(NOTICE, message)


def _mask_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive fields in request data.

    Args:
        data: The data dictionary to mask.

    Returns:
        A new dictionary with sensitive fields masked.
    """
    sensitive_keys = {
        "auth_key",
        "password",
        "p",
        "vkey",
        "web_password",
        "basic_password",
    }
    masked = {}
    for key, value in data.items():
        if key.lower() in sensitive_keys and value:
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by name.

    Args:
        name: Logger name (typically module name like "nps_ctl.base").

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


def get_operation_logger(name: str) -> OperationLogger:
    """Get an OperationLogger instance for structured logging.

    Args:
        name: Logger name (typically module name like "nps_ctl.base").

    Returns:
        OperationLogger instance.
    """
    return OperationLogger(logging.getLogger(name))


class FlushingStreamHandler(logging.StreamHandler):
    """StreamHandler that flushes after every emit.

    This ensures log messages are immediately visible, even when output
    is piped or goes through proxies (like SSH SOCKS tunnels).
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record and flush the stream."""
        super().emit(record)
        self.flush()


def configure_logging(
    level: str | int = "NOTICE",
    use_colors: bool = True,
    handler: logging.Handler | None = None,
) -> None:
    """Configure logging for the nps_ctl package.

    This function sets up the root logger for the nps_ctl package with
    the specified log level and formatter.

    Args:
        level: Log level (DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL) or int.
            Default is NOTICE (25), which shows key phase information.
        use_colors: Whether to use colored output.
        handler: Custom handler to use. If None, uses FlushingStreamHandler to stderr.

    Example:
        >>> configure_logging(level="DEBUG")
        >>> configure_logging(level="INFO")  # Show all request details
        >>> configure_logging(level="NOTICE")  # Default, show key phases only
    """
    # Convert string level to int if needed
    if isinstance(level, str):
        level_upper = level.upper()
        if level_upper == "NOTICE":
            level = NOTICE
        else:
            level = getattr(logging, level_upper, NOTICE)

    # Get the root logger for nps_ctl
    root_logger = logging.getLogger("nps_ctl")
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create handler if not provided
    # Use FlushingStreamHandler to ensure immediate output
    if handler is None:
        handler = FlushingStreamHandler(sys.stderr)

    # Set formatter
    handler.setFormatter(NPSLogFormatter(use_colors=use_colors))
    handler.setLevel(level)

    # Add handler
    root_logger.addHandler(handler)

    # Prevent propagation to root logger
    root_logger.propagate = False


def set_log_level(level: str | int) -> None:
    """Set the log level for the nps_ctl package.

    Args:
        level: Log level (DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL) or int.
    """
    if isinstance(level, str):
        level_upper = level.upper()
        if level_upper == "NOTICE":
            level = NOTICE
        else:
            level = getattr(logging, level_upper, NOTICE)

    logger = logging.getLogger("nps_ctl")
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)


class FlushingConsole(Console):
    """Console that flushes output after every print.

    This ensures immediate output visibility when running through
    SSH SOCKS proxies or other tunneled connections where output
    buffering can cause delays.

    When using --auto-proxy, PySocks replaces the global socket.socket,
    which can affect Python's TTY detection and trigger full buffering
    instead of line buffering. This class ensures output is flushed
    immediately after every print call.

    Example:
        >>> from nps_ctl.logging import FlushingConsole
        >>> console = FlushingConsole(force_terminal=True)
        >>> console.print("[green]This will be visible immediately[/green]")
    """

    def print(
        self,
        *objects: Any,
        **kwargs: Any,
    ) -> None:
        """Print and immediately flush output."""
        super().print(*objects, **kwargs)
        # Flush the underlying file to ensure immediate output
        if self.file:
            self.file.flush()


def flush_output() -> None:
    """Flush stdout and stderr to ensure immediate output.

    This is critical when running through SSH SOCKS proxies or other
    tunneled connections where output buffering can cause delays.
    """
    sys.stdout.flush()
    sys.stderr.flush()
