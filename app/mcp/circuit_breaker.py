"""
Thread-safe Circuit Breaker pattern implementation for AI Tool Calling.
Protects AI agents from cascading timeouts and prevents hammering degraded microservices.
States:
  - CLOSED: Normal operation. Invocations pass through.
  - OPEN: Tripped after N consecutive failures. Fast-fails immediately.
  - HALF_OPEN: Cooldown expired. Allows a trial execution to test health.
"""

import time
import threading
from enum import Enum
from typing import Dict, Optional, Callable, Any


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when an execution is attempted on an OPEN circuit."""
    def __init__(self, name: str, retry_after: float):
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. Target service is degraded. "
            f"Fast-failing to protect agent budget. Retry allowed in {retry_after:.1f}s."
        )
        self.name = name
        self.retry_after = retry_after


class CircuitBreaker:
    """Stateful circuit breaker for a specific microservice or diagnostic tool."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if cooldown period elapsed to enter HALF_OPEN
                if time.time() - (self._opened_at or 0) >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
            return self._state

    def record_success(self):
        """Records a successful operation and restores health if in HALF_OPEN."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._opened_at = None
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self):
        """Records a failure and trips the breaker if threshold reached."""
        with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.time()

    def before_execution(self):
        """Pre-check before tool execution. Raises CircuitBreakerOpenException if OPEN."""
        current_state = self.state
        if current_state == CircuitState.OPEN:
            elapsed = time.time() - (self._opened_at or 0)
            remaining = max(0.0, self.recovery_timeout - elapsed)
            raise CircuitBreakerOpenException(self.name, remaining)

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Executes a callable wrapped with circuit breaker safety."""
        self.before_execution()
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def trip(self):
        """Manually trip the circuit breaker for testing or administrative intervention."""
        with self._lock:
            self._state = CircuitState.OPEN
            self._opened_at = time.time()

    def reset(self):
        """Manually reset the circuit breaker to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = None


class CircuitBreakerManager:
    """Registry maintaining circuit breakers per service or tool."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_breaker(self, name: str) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=self.failure_threshold,
                    recovery_timeout=self.recovery_timeout
                )
            return self._breakers[name]

    def reset_all(self):
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()
