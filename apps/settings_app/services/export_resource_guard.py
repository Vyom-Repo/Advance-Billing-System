"""
apps/settings_app/services/export_resource_guard.py

Process-local bounded resource guard for heavy export and backup generation tasks.
Prevents worker memory exhaustion by bounding maximum concurrent active exports.
"""

import contextlib
import logging
import threading

logger = logging.getLogger(__name__)


class ExportCapacityExceededError(Exception):
    """Raised when maximum concurrent export generation slots are exhausted."""

    pass


class ExportResourceGuard:
    MAX_CONCURRENT_EXPORTS = 2
    _semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_EXPORTS)
    _active_lock = threading.Lock()
    _active_exports = 0

    @classmethod
    def get_max_concurrent(cls) -> int:
        return cls.MAX_CONCURRENT_EXPORTS

    @classmethod
    def get_active_exports(cls) -> int:
        with cls._active_lock:
            return cls._active_exports

    @classmethod
    def reset_stats(cls):
        with cls._active_lock:
            cls._active_exports = 0
            cls._semaphore = threading.BoundedSemaphore(cls.MAX_CONCURRENT_EXPORTS)

    @classmethod
    @contextlib.contextmanager
    def protect(cls, timeout: float = 2.0):
        """
        Context manager to bound concurrent active export generation operations per process.
        Raises ExportCapacityExceededError if a slot cannot be acquired within timeout.
        """
        acquired = cls._semaphore.acquire(blocking=True, timeout=timeout)
        if not acquired:
            logger.warning(
                f"Export generation slot request timed out after {timeout}s (active={cls.get_active_exports()}/{cls.MAX_CONCURRENT_EXPORTS})"
            )
            raise ExportCapacityExceededError(
                "Export generation system is currently processing maximum capacity. Please try again in a few seconds."
            )

        with cls._active_lock:
            cls._active_exports += 1

        logger.info(
            f"Export generation slot acquired (active={cls.get_active_exports()}/{cls.MAX_CONCURRENT_EXPORTS})"
        )

        try:
            yield
        finally:
            with cls._active_lock:
                cls._active_exports = max(0, cls._active_exports - 1)
            cls._semaphore.release()
            logger.info(
                f"Export generation slot released (active={cls.get_active_exports()}/{cls.MAX_CONCURRENT_EXPORTS})"
            )
