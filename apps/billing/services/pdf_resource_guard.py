"""
apps/billing/services/pdf_resource_guard.py

Central application-level PDF resource guard for WeasyPrint execution.

Enforces a hard process-local concurrency limit on WeasyPrint PDF generation
to prevent CPU/RAM exhaustion under heavy request load.

Requirements:
- Process-local, thread-safe.
- Maximum concurrent WeasyPrint renders = 2 per application process.
- Bounded semaphore slot release guaranteed via try...finally.
- Controlled rejection (PDFCapacityExceededError) if slot is unavailable.
"""

import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PDFCapacityExceededError(Exception):
    """Raised when maximum concurrent PDF renders are in progress."""
    pass


class PDFResourceGuard:
    _MAX_CONCURRENT_RENDERS = 2
    _semaphore = threading.BoundedSemaphore(_MAX_CONCURRENT_RENDERS)
    _active_renders = 0
    _active_lock = threading.Lock()
    _max_observed_active = 0  # For telemetry and concurrency test verification

    @classmethod
    def get_max_concurrent(cls) -> int:
        return cls._MAX_CONCURRENT_RENDERS

    @classmethod
    def get_active_renders(cls) -> int:
        with cls._active_lock:
            return cls._active_renders

    @classmethod
    def get_max_observed_active(cls) -> int:
        with cls._active_lock:
            return cls._max_observed_active

    @classmethod
    def reset_stats(cls) -> None:
        """Reset telemetry counters (used primarily in test teardown/setup)."""
        with cls._active_lock:
            cls._max_observed_active = cls._active_renders

    @classmethod
    @contextmanager
    def protect(cls, timeout: float = 2.0):
        """
        Context manager that guards WeasyPrint rendering operations.

        Acquires a slot in the bounded semaphore (wait up to `timeout` seconds).
        If acquired, yields control and guarantees slot release via try...finally.
        If timeout expires, raises PDFCapacityExceededError.
        """
        acquired = cls._semaphore.acquire(blocking=True, timeout=timeout)
        if not acquired:
            logger.warning(
                "PDF render capacity exhausted (max=%d). Request rejected.",
                cls._MAX_CONCURRENT_RENDERS,
            )
            raise PDFCapacityExceededError(
                "PDF rendering capacity is temporarily exhausted. Please try again later."
            )

        with cls._active_lock:
            cls._active_renders += 1
            cls._max_observed_active = max(cls._max_observed_active, cls._active_renders)
            logger.info(
                "PDF render slot acquired (active=%d/%d)",
                cls._active_renders,
                cls._MAX_CONCURRENT_RENDERS,
            )

        try:
            yield
        finally:
            with cls._active_lock:
                cls._active_renders -= 1
                logger.info(
                    "PDF render slot released (active=%d/%d)",
                    cls._active_renders,
                    cls._MAX_CONCURRENT_RENDERS,
                )
            cls._semaphore.release()
