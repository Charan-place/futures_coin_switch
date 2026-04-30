"""
In-memory ring buffer for log lines + a logging.Handler that feeds it.

Why this exists:
  The rich dashboard calls `console.clear()` on every refresh — which means
  every `[INFO]` line scrolling above it gets wiped instantly. The user's
  screenshot showed only one log line ("Scanning 12 pairs for signals...")
  because that was simply the last line printed before the next dashboard
  redraw.

  The fix: capture log records in a process-wide deque and render them
  inside the dashboard as their own panel. They stay visible across
  redraws.
"""
import logging
import threading
from collections import deque
from datetime import datetime
from typing import Deque, List, Tuple


class BotLog:
    """Thread-safe rolling buffer of (timestamp, level, name, message)."""

    _instance: "BotLog | None" = None

    def __init__(self, capacity: int = 400):
        self._records: Deque[Tuple[str, str, str, str]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "BotLog":
        if cls._instance is None:
            cls._instance = BotLog()
        return cls._instance

    def append(self, level: str, name: str, message: str) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        with self._lock:
            self._records.append((ts, level, name, message))

    def tail(self, n: int = 25) -> List[Tuple[str, str, str, str]]:
        with self._lock:
            return list(self._records)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


class BufferedHandler(logging.Handler):
    """Logging handler that pushes records into the BotLog ring buffer."""

    def __init__(self, level: int = logging.INFO):
        super().__init__(level)

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            BotLog.get().append(record.levelname, record.name, record.getMessage())
        except Exception:
            self.handleError(record)


def install_buffered_handler(level: int = logging.INFO) -> None:
    """Attach a BufferedHandler to the root logger (idempotent)."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, BufferedHandler):
            return
    handler = BufferedHandler(level=level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)


def silence_stdout_logging() -> None:
    """
    Remove every StreamHandler that writes to stdout/stderr from the root
    logger AND from any child logger that has its own handlers. The Bot Log
    panel inside the dashboard already shows everything; this stops `print`
    from tearing the rich layout.
    File handlers (disk logs) are preserved.
    """
    import sys
    targets = (sys.stdout, sys.stderr)

    def _strip(logger_obj: logging.Logger) -> None:
        for h in list(logger_obj.handlers):
            if isinstance(h, logging.StreamHandler) and not isinstance(h, BufferedHandler):
                stream = getattr(h, "stream", None)
                if stream is None or stream in targets:
                    logger_obj.removeHandler(h)

    _strip(logging.getLogger())
    for name in list(logging.Logger.manager.loggerDict.keys()):
        obj = logging.getLogger(name)
        if isinstance(obj, logging.Logger) and obj.handlers:
            _strip(obj)
