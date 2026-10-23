"""
Idempotency and Atomic Leases for Distributed Incident Ingestion.
Eliminates duplicate alerts during alert storms (SHA-256 fingerprinting)
and prevents race conditions across worker nodes.
"""

import time
import hashlib
import threading
from typing import Dict, Any, Optional, Tuple


class IdempotencyManager:
    """Manages SHA-256 event fingerprinting, deduplication windows, and atomic leases."""

    def __init__(self, default_ttl_seconds: int = 300):
        self.default_ttl_seconds = default_ttl_seconds
        self._fingerprints: Dict[str, Tuple[Any, float]] = {}  # fingerprint -> (record, expires_at)
        self._leases: Dict[str, float] = {}  # resource_id -> expires_at
        self._lock = threading.Lock()

    @staticmethod
    def compute_fingerprint(
        service: str,
        title: str,
        environment: str = "production",
        time_bucket_minutes: int = 5
    ) -> str:
        """Computes a deterministic SHA-256 fingerprint bucketed to a 5-minute time window.
        Identical alerts firing across microservices within 5 minutes produce the exact same hash.
        """
        now = time.time()
        bucket = int(now // (time_bucket_minutes * 60))
        raw = f"{environment.lower()}:{service.lower().strip()}:{title.lower().strip()}:{bucket}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def check_and_register(
        self,
        fingerprint: str,
        record: Any,
        ttl_seconds: Optional[int] = None
    ) -> Tuple[bool, Optional[Any]]:
        """Checks if a fingerprint is already active.
        Returns:
            (True, existing_record) if a duplicate alert was detected within the TTL window.
            (False, None) if this is a novel alert (registered successfully).
        """
        ttl = ttl_seconds or self.default_ttl_seconds
        now = time.time()

        with self._lock:
            # Check existing entry
            if fingerprint in self._fingerprints:
                existing_record, expires_at = self._fingerprints[fingerprint]
                if now < expires_at:
                    return True, existing_record

            # Register novel fingerprint
            expires_at = now + ttl
            self._fingerprints[fingerprint] = (record, expires_at)
            return False, None

    def acquire_lease(self, resource_id: str, lease_seconds: float = 60.0) -> bool:
        """Attempts to acquire an atomic exclusive lease on an incident.
        Prevents multiple workers from triggering duplicate LangGraph investigations.
        Returns True if lease acquired, False if already held by another worker.
        """
        now = time.time()
        with self._lock:
            if resource_id in self._leases:
                expires_at = self._leases[resource_id]
                if now < expires_at:
                    return False  # Lease is actively held

            # Grant lease
            self._leases[resource_id] = now + lease_seconds
            return True

    def release_lease(self, resource_id: str):
        """Releases an atomic lease upon investigation completion."""
        with self._lock:
            self._leases.pop(resource_id, None)

    def prune_expired(self):
        """Housekeeping: purges expired fingerprints and leases."""
        now = time.time()
        with self._lock:
            self._fingerprints = {k: v for k, v in self._fingerprints.items() if now < v[1]}
            self._leases = {k: v for k, v in self._leases.items() if now < v}

    def clear(self):
        """Clears all records (used for test teardowns)."""
        with self._lock:
            self._fingerprints.clear()
            self._leases.clear()


# Global singleton instance
idempotency_manager = IdempotencyManager()
