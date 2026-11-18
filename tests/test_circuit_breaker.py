"""
Unit Tests for Circuit Breaker Pattern in Model Routing.
Verifies CLOSED -> OPEN transitions on 429, fast skipping of degraded models,
cooldown expiration to HALF_OPEN, and recovery to CLOSED.
"""

import unittest
import time
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from kernel.types import ModelConfig, WorkspaceSnapshot, ExecutionPayload
from kernel.models import ModelRegistry, RateLimitException, MockModelClient
from kernel.router import FailoverRouter
from kernel.circuit_breaker import CircuitBreakerManager


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.config = ModelConfig(
            name="test-model",
            provider="mock",
            model_id="mock-test",
            cooldown_seconds=0.2,  # Short cooldown for test
            failure_threshold=2
        )

    def test_normal_closed_state(self):
        can_run, reason = CircuitBreakerManager.can_execute(self.config)
        self.assertTrue(can_run)
        self.assertEqual(self.config.circuit_state, "CLOSED")

    def test_immediate_trip_on_429(self):
        # 429 Trips breaker immediately
        CircuitBreakerManager.record_failure(self.config, RateLimitException("HTTP 429"))
        self.assertEqual(self.config.circuit_state, "OPEN")

        # Immediate next check should be disallowed
        can_run, reason = CircuitBreakerManager.can_execute(self.config)
        self.assertFalse(can_run)
        self.assertIn("Circuit is OPEN", reason)

    def test_cooldown_and_recovery(self):
        # Trip to OPEN
        CircuitBreakerManager.record_failure(self.config, RateLimitException("HTTP 429"))
        self.assertEqual(self.config.circuit_state, "OPEN")

        # Wait for cooldown to expire
        time.sleep(0.25)

        # Should transition to HALF_OPEN
        can_run, reason = CircuitBreakerManager.can_execute(self.config)
        self.assertTrue(can_run)
        self.assertEqual(self.config.circuit_state, "HALF_OPEN")

        # Success in HALF_OPEN resets to CLOSED
        CircuitBreakerManager.record_success(self.config)
        self.assertEqual(self.config.circuit_state, "CLOSED")
        self.assertEqual(self.config.failure_count, 0)

    def test_fast_skip_in_router(self):
        registry = ModelRegistry()
        primary_cfg = ModelConfig(
            name="flaky-primary",
            provider="mock",
            model_id="mock-1",
            priority=1,
            cooldown_seconds=10.0,
            circuit_state="OPEN",
            last_failure_time=time.time()
        )
        fallback_cfg = ModelConfig(
            name="steady-fallback",
            provider="mock",
            model_id="mock-2",
            priority=2,
            is_fallback=True
        )
        registry.register(primary_cfg)
        registry.register(fallback_cfg)

        router = FailoverRouter(registry)
        payload = ExecutionPayload(
            task_prompt="Implement task",
            workspace_snapshot=WorkspaceSnapshot(active_file=None, open_files={}, recent_history=[])
        )

        resp, notes = router.execute_with_failover(
            payload=payload,
            primary_model_name="flaky-primary",
            fallback_models=["steady-fallback"]
        )

        self.assertEqual(resp.model_name, "steady-fallback")
        self.assertTrue(len(notes) > 0)
        self.assertIn("[CIRCUIT BREAKER]", notes[0])
        self.assertIn("flaky-primary", notes[0])


if __name__ == "__main__":
    unittest.main()
