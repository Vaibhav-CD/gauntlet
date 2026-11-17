"""
End-to-End Integration Test for System Kernel.
Demonstrates:
1. Centralized Workspace State & Snapshot integrity.
2. Surgical block replacement mutation with zero copy-pasting.
3. Transparent failover on HTTP 429 Rate Limit with handoff notes.
4. Rollback capability.
"""

import os
import shutil
import tempfile
import unittest
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from kernel.engine import SystemKernel
from kernel.types import ExecutionPayload


class TestIntegrationWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kernel_integration_")
        # Copy demo files
        demo_src = Path(__file__).parent.parent / "demo_workspace"
        for item in demo_src.iterdir():
            if item.is_file():
                shutil.copy(item, Path(self.temp_dir) / item.name)

        self.kernel = SystemKernel(project_root=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_lifecycle(self):
        # 1. Open file into snapshot buffer
        self.kernel.state_manager.open_file("math_utils.py", set_as_active=True)
        snapshot = self.kernel.state_manager.get_snapshot()

        self.assertEqual(snapshot.active_file, "math_utils.py")
        self.assertIn("math_utils.py", snapshot.open_files)
        self.assertIn("# TODO: Implement calculation", snapshot.open_files["math_utils.py"])

        # 2. Execute task to fix the calculation
        result = self.kernel.execute(
            task_prompt="Please fix and implement the calculate_metrics function in math_utils.py"
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.model_used, "primary-mock")
        self.assertTrue(len(result.mutations_applied) > 0)
        self.assertTrue(result.mutations_applied[0].success)

        # Verify open buffer was automatically updated without copy-pasting
        updated_code = self.kernel.state_manager.snapshot.open_files["math_utils.py"]
        self.assertNotIn("# TODO: Implement calculation", updated_code)
        self.assertIn("Fixed and implemented by primary-mock", updated_code)

        # Verify disk was also updated
        disk_code = (Path(self.temp_dir) / "math_utils.py").read_text(encoding="utf-8")
        self.assertIn("Fixed and implemented by primary-mock", disk_code)

        # 3. Simulate HTTP 429 Rate Limit on Primary Model
        primary_cfg = self.kernel.registry.get_config("primary-mock")
        primary_cfg.simulate_429 = True

        # 4. Execute another task requiring file creation
        failover_res = self.kernel.execute(
            task_prompt="Create file tests/test_math.py with unit tests"
        )

        # Verify transparent failover
        self.assertEqual(failover_res.status, "failover_success")
        self.assertEqual(failover_res.model_used, "fallback-mock")
        self.assertTrue(len(failover_res.handoff_notes) > 0)
        self.assertIn("HTTP 429 Rate Limit", failover_res.handoff_notes[0])

        # Verify test file was created on disk and in buffer
        self.assertIn("tests/test_math.py", self.kernel.state_manager.snapshot.open_files)
        created_disk = Path(self.temp_dir) / "tests" / "test_math.py"
        self.assertTrue(created_disk.exists())

        # 5. Verify temporal continuity in recent_history
        history = self.kernel.state_manager.snapshot.recent_history
        self.assertTrue(len(history) >= 4)  # 2 user prompts + 2 assistant responses
        latest_turn = history[-1]
        self.assertEqual(latest_turn.role, "assistant")
        self.assertEqual(latest_turn.model_name, "fallback-mock")
        self.assertTrue(len(latest_turn.handoff_notes) > 0)

        # 6. Test rollback
        restored_snap = self.kernel.state_manager.rollback()
        self.assertIsNotNone(restored_snap)


if __name__ == "__main__":
    unittest.main()
