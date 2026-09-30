"""Retry/backoff and circuit-breaker primitives (clock, sleep and RNG are injectable for tests)."""
from __future__ import annotations

import random
import threading
import time
from typing import Callable


class CircuitBreaker:
    """closed -> (N consecutive failures) -> open -> (cooldown) -> half-open (1 trial) -> closed/open."""

    def __init__(self, threshold: int = 5, cooldown_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.threshold = max(1, threshold)
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._trial = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            return "half-open" if self._clock() - self._opened_at >= self.cooldown_s else "open"

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at >= self.cooldown_s and not self._trial:
                self._trial = True          # exactly one probe request
                return True
            return False

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._trial = False

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._trial = False
            if self._failures >= self.threshold:
                self._opened_at = self._clock()


def backoff_delay(attempt: int, base: float, cap: float, rand: Callable[[], float] = random.random) -> float:
    """Exponential backoff with 'full jitter' in [cap_i/2, cap_i], attempt starts at 0."""
    ceiling = min(cap, base * (2 ** attempt))
    return ceiling / 2 + rand() * ceiling / 2
