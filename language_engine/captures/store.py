"""Owner-scoped, byte-bounded snapshot storage and upload throttling.

The application currently runs one worker; captures are intentionally ephemeral
and local to that worker, and are never written alongside application assets.
"""
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
import threading
import time


class CaptureTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class Capture:
    owner: str
    html: str
    url: str
    title: str
    created_at: str
    expires_at: float
    size: int


class CaptureStore:
    def __init__(self, *, max_bytes, total_bytes, max_items, ttl,
                 uploads_per_minute, clock=time.monotonic):
        if min(max_bytes, total_bytes, max_items, ttl, uploads_per_minute) <= 0:
            raise ValueError("Capture limits must be positive")
        self.max_bytes = min(max_bytes, total_bytes)
        self.total_bytes = total_bytes
        self.max_items = max_items
        self.ttl = ttl
        self.uploads_per_minute = uploads_per_minute
        self.clock = clock
        self._records = OrderedDict()
        self._uploads = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def _remove(self, token):
        self._bytes -= self._records.pop(token).size

    def _prune(self, now):
        for token, record in list(self._records.items()):
            if record.expires_at <= now:
                self._remove(token)
        for owner, times in list(self._uploads.items()):
            while times and times[0] <= now - 60:
                times.popleft()
            if not times:
                del self._uploads[owner]

    def allow_upload(self, owner):
        with self._lock:
            now = self.clock()
            self._prune(now)
            # Bound the limiter itself; do not evict active limits to admit abuse.
            if owner not in self._uploads and len(self._uploads) >= 1024:
                return False
            times = self._uploads.setdefault(owner, deque())
            if len(times) >= self.uploads_per_minute:
                return False
            times.append(now)
            return True

    def put(self, owner, html, url, title):
        size = len(html.encode("utf-8"))
        if size > self.max_bytes:
            raise CaptureTooLarge("Captured HTML exceeds the size limit")
        with self._lock:
            now = self.clock()
            self._prune(now)
            while self._records and (len(self._records) >= self.max_items
                                     or self._bytes + size > self.total_bytes):
                self._remove(next(iter(self._records)))
            token = secrets.token_urlsafe(24)
            self._records[token] = Capture(owner, html, url, title,
                                          datetime.now(timezone.utc).isoformat(),
                                          now + self.ttl, size)
            self._bytes += size
            return token

    def get(self, owner, token):
        with self._lock:
            self._prune(self.clock())
            record = self._records.get(token)
            if record is None or record.owner != owner:
                return None
            self._records.move_to_end(token)
            return record
