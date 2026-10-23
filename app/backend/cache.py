"""
Redis & In-Memory Cache-Aside Layer for High-Frequency Topology and Metric Lookups.
Implements the Cache-Aside (Lazy Loading) pattern with TTL expiry and telemetry hit tracking.
"""

import time
import json
import logging
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheAsideManager:
    """Manages cache-aside operations for distributed topology graphs and Golden Signal metrics."""

    def __init__(self, default_ttl_seconds: int = 300):
        self.default_ttl_seconds = default_ttl_seconds
        self._memory_cache: Dict[str, Tuple[Any, float]] = {}  # key -> (data, expires_at)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Fetches an entry from cache if present and unexpired."""
        # Check Redis if configured
        if settings.stream_backend == "redis":
            try:
                import redis
                r = redis.from_url(settings.redis_url)
                val = r.get(key)
                if val is not None:
                    with self._lock:
                        self._hits += 1
                    return json.loads(val)
            except Exception:
                pass  # Fallback to in-memory cache

        # Fallback in-memory
        now = time.time()
        with self._lock:
            if key in self._memory_cache:
                data, expires_at = self._memory_cache[key]
                if now < expires_at:
                    self._hits += 1
                    return data
                else:
                    self._memory_cache.pop(key, None)
            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """Sets a cached entry with TTL."""
        ttl = ttl_seconds or self.default_ttl_seconds
        now = time.time()

        if settings.stream_backend == "redis":
            try:
                import redis
                r = redis.from_url(settings.redis_url)
                r.setex(key, ttl, json.dumps(value, default=str))
                return
            except Exception:
                pass

        with self._lock:
            self._memory_cache[key] = (value, now + ttl)

    def delete(self, key: str):
        """Invalidates a cache key."""
        with self._lock:
            self._memory_cache.pop(key, None)

    def cached_lookup(
        self,
        key: str,
        fetcher: Callable[[], Any],
        ttl_seconds: Optional[int] = None,
    ) -> Tuple[Any, bool]:
        """Standard Cache-Aside pattern:
        1. Read from cache.
        2. On HIT: return (cached_data, True).
        3. On MISS: invoke fetcher(), store in cache with TTL, return (fresh_data, False).
        """
        cached = self.get(key)
        if cached is not None:
            return cached, True

        # Cache miss: query authoritative source
        fresh = fetcher()
        self.set(key, fresh, ttl_seconds=ttl_seconds)
        return fresh, False

    def get_topology(
        self,
        service_name: str,
        direction: str = "downstream",
        max_depth: int = 3,
        fetcher: Optional[Callable[[], Any]] = None,
        ttl_seconds: int = 300,
    ) -> Tuple[Any, bool]:
        """Cache-aside helper for repeated service dependency graph traversals."""
        key = f"cache:topology:{service_name.lower().strip()}:{direction}:{max_depth}"
        if fetcher:
            return self.cached_lookup(key, fetcher, ttl_seconds=ttl_seconds)
        return self.get(key), self.get(key) is not None

    def get_metrics(
        self,
        service_name: str,
        metric_name: str,
        fetcher: Optional[Callable[[], Any]] = None,
        ttl_seconds: int = 60,
    ) -> Tuple[Any, bool]:
        """Cache-aside helper for high-frequency SRE Golden Signal metric lookups."""
        key = f"cache:metrics:{service_name.lower().strip()}:{metric_name.lower().strip()}"
        if fetcher:
            return self.cached_lookup(key, fetcher, ttl_seconds=ttl_seconds)
        return self.get(key), self.get(key) is not None

    @property
    def stats(self) -> Dict[str, Any]:
        """Returns cache telemetry and hit-rate percentage."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_queries": total,
                "hit_rate_pct": round(hit_rate, 2),
                "cached_keys_count": len(self._memory_cache),
            }

    def clear(self):
        """Clears all cached records and resets counters."""
        with self._lock:
            self._memory_cache.clear()
            self._hits = 0
            self._misses = 0


# Global singleton instance
cache_manager = CacheAsideManager()
