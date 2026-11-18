"""
Circuit Breaker Pattern for Resilient Model Routing.
Prevents hammering degraded or rate-limited models by tracking failure states,
enforcing cooldown windows, and probing with canary requests.
"""

import time
from typing import Tuple, Optional
from .types import ModelConfig, CircuitState
from .models.base import RateLimitException


class CircuitBreakerManager:
    """
    Manages the circuit breaker lifecycle for AI model clients:
    - CLOSED: Normal operation, requests are allowed.
    - OPEN: Model tripped by HTTP 429 or repeated errors. Requests are fast-failed/skipped.
    - HALF_OPEN: Cooldown expired, allows a single canary request to test recovery.
    """

    @classmethod
    def can_execute(cls, config: ModelConfig) -> Tuple[bool, Optional[str]]:
        """
        Determines whether a model is eligible for invocation.
        Returns:
            (allow: bool, reason: Optional[str])
        """
        now = time.time()

        if config.circuit_state == "CLOSED":
            return True, None

        if config.circuit_state == "OPEN":
            if config.last_failure_time is None:
                config.last_failure_time = now

            elapsed = now - config.last_failure_time
            if elapsed >= config.cooldown_seconds:
                # Transition to HALF_OPEN to test a canary request
                config.circuit_state = "HALF_OPEN"
                return True, "cooldown_expired_testing_canary"
            else:
                remaining = round(config.cooldown_seconds - elapsed, 1)
                return False, f"Circuit is OPEN (cooldown active, {remaining}s remaining)"

        if config.circuit_state == "HALF_OPEN":
            return True, "canary_probe"

        return True, None

    @classmethod
    def record_success(cls, config: ModelConfig):
        """Resets the circuit to healthy CLOSED state upon a successful response."""
        config.circuit_state = "CLOSED"
        config.failure_count = 0
        config.last_failure_time = None

    @classmethod
    def record_failure(cls, config: ModelConfig, exception: Exception):
        """
        Updates the circuit state on failure.
        HTTP 429 trips the breaker immediately. Other errors trip after failure_threshold.
        """
        config.failure_count += 1
        config.last_failure_time = time.time()

        # Immediate trip on rate limit or when exceeding threshold
        if isinstance(exception, RateLimitException) or config.failure_count >= config.failure_threshold:
            config.circuit_state = "OPEN"

    @classmethod
    def reset_circuit(cls, config: ModelConfig):
        """Manually closes and resets the circuit breaker."""
        config.circuit_state = "CLOSED"
        config.failure_count = 0
        config.last_failure_time = None
