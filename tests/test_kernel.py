"""
Comprehensive Test Suite for System Kernel Multi-Model Developer Environment.
Tests State Management, Dynamic Model Agnosticism, Transparent Failover (429/timeout),
Handoff Notes, and Automatic State Mutation.
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

from kernel.types import (
    WorkspaceSnapshot,
    ExecutionPayload,
    CodeMutation,
    BlockReplacement,
    ModelConfig
)
from kernel.state_manager import WorkspaceStateManager
from kernel.prompt_engine import PromptEngine
from kernel.mutation_parser import MutationParser
from kernel.models import (
    ModelRegistry,
    MockModelClient,
    RateLimitException,
    TimeoutException
)
from kernel.router import FailoverRouter
from kernel.engine import SystemKernel


class TestWorkspaceStateManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="kernel_test_")
        self.state_mgr = WorkspaceStateManager(project_root=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_open_and_active_file(self):
        sample_path = Path(self.test_dir) / "main.py"
        sample_path.write_text("print('hello world')", encoding="utf-8")

        content = self.state_mgr.open_file("main.py", set_as_active=True)
        self.assertEqual(content, "print('hello world')")
        self.assertEqual(self.state_mgr.snapshot.active_file, "main.py")
        self.assertIn("main.py", self.state_mgr.snapshot.open_files)

    def test_block_replacement_mutation(self):
        sample_path = Path(self.test_dir) / "calc.py"
        initial_code = "def calculate():\n    # TODO: implement\n    pass\n"
        sample_path.write_text(initial_code, encoding="utf-8")
        self.state_mgr.open_file("calc.py")

        mutation = CodeMutation(
            action="replace_block",
            file_path="calc.py",
            block_replacement=BlockReplacement(
                search="# TODO: implement\n    pass",
                replace="return 42"
            )
        )
        applied = self.state_mgr.apply_mutation(mutation, write_to_disk=True)
        self.assertTrue(applied.success)
        self.assertIn("return 42", self.state_mgr.snapshot.open_files["calc.py"])

        # Verify disk file updated
        disk_content = sample_path.read_text(encoding="utf-8")
        self.assertIn("return 42", disk_content)

    def test_rollback(self):
        sample_path = Path(self.test_dir) / "app.py"
        sample_path.write_text("v1 = 100", encoding="utf-8")
        self.state_mgr.open_file("app.py")

        # Mutate to v2
        mutation = CodeMutation(
            action="update",
            file_path="app.py",
            content="v2 = 200"
        )
        self.state_mgr.apply_mutation(mutation, write_to_disk=True)
        self.assertEqual(self.state_mgr.snapshot.open_files["app.py"], "v2 = 200")

        # Rollback
        restored = self.state_mgr.rollback()
        self.assertIsNotNone(restored)
        self.assertEqual(self.state_mgr.snapshot.open_files["app.py"], "v1 = 100")
        self.assertEqual(sample_path.read_text(encoding="utf-8"), "v1 = 100")


class TestFailoverRouter(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry()

        # Primary model configured to simulate HTTP 429
        self.primary_cfg = ModelConfig(
            name="primary-429",
            provider="mock",
            model_id="mock-primary",
            priority=1,
            simulate_429=True
        )
        self.registry.register(self.primary_cfg)

        # Fallback model healthy
        self.fallback_cfg = ModelConfig(
            name="fallback-healthy",
            provider="mock",
            model_id="mock-fallback",
            priority=2,
            is_fallback=True
        )
        self.registry.register(self.fallback_cfg)

        self.router = FailoverRouter(self.registry)

    def test_transparent_failover_on_429(self):
        payload = ExecutionPayload(
            task_prompt="Create a helper function",
            workspace_snapshot=WorkspaceSnapshot(
                active_file="src/utils.py",
                open_files={"src/utils.py": "def helper(): pass"},
                recent_history=[]
            )
        )

        response, handoff_notes = self.router.execute_with_failover(
            payload=payload,
            primary_model_name="primary-429",
            fallback_models=["fallback-healthy"]
        )

        # Verified that fallback model succeeded
        self.assertEqual(response.model_name, "fallback-healthy")
        # Verified that handoff note was generated preserving context
        self.assertTrue(len(handoff_notes) > 0)
        self.assertIn("HTTP 429 Rate Limit", handoff_notes[0])
        self.assertIn("primary-429", handoff_notes[0])

    def test_timeout_failover(self):
        timeout_cfg = ModelConfig(
            name="primary-timeout",
            provider="mock",
            model_id="mock-timeout",
            priority=1,
            simulate_timeout=True
        )
        self.registry.register(timeout_cfg)

        payload = ExecutionPayload(
            task_prompt="Refactor code",
            workspace_snapshot=WorkspaceSnapshot(active_file=None, open_files={}, recent_history=[])
        )

        response, handoff_notes = self.router.execute_with_failover(
            payload=payload,
            primary_model_name="primary-timeout",
            fallback_models=["fallback-healthy"]
        )

        self.assertEqual(response.model_name, "fallback-healthy")
        self.assertIn("timed out (HTTP 408)", handoff_notes[0])


class TestMutationParser(unittest.TestCase):
    def test_parse_block_replacement(self):
        raw = """Here is the fix:
<<<SEARCH_REPLACE:src/math.py>>>
<<<<<<< SEARCH
def add(a, b):
    return a - b
=======
def add(a, b):
    return a + b
>>>>>>>
<<<END_SEARCH_REPLACE>>>
Enjoy!"""
        explanation, mutations = MutationParser.parse(raw)
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0].action, "replace_block")
        self.assertEqual(mutations[0].file_path, "src/math.py")
        self.assertEqual(mutations[0].block_replacement.search.strip(), "def add(a, b):\n    return a - b")
        self.assertEqual(mutations[0].block_replacement.replace.strip(), "def add(a, b):\n    return a + b")
        self.assertIn("Applied block replacement to `src/math.py`", explanation)

    def test_parse_file_update(self):
        raw = """Creating new file:
<<<FILE_UPDATE:config.json>>>
{
  "theme": "dark"
}
<<<END_FILE_UPDATE>>>
Done."""
        explanation, mutations = MutationParser.parse(raw)
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0].action, "update")
        self.assertEqual(mutations[0].file_path, "config.json")
        self.assertIn('"theme": "dark"', mutations[0].content)


class TestSystemKernelEndToEnd(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="kernel_e2e_")
        self.kernel = SystemKernel(project_root=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_file_execution(self):
        res = self.kernel.execute("Please create file src/service.py")
        self.assertEqual(res.status, "success")
        self.assertTrue(len(res.mutations_applied) > 0)
        self.assertIn("src/service.py", res.updated_snapshot.open_files)
        # Check disk
        disk_path = Path(self.test_dir) / "src" / "service.py"
        self.assertTrue(disk_path.exists())

    def test_failover_execution_with_history(self):
        # Configure primary mock to simulate 429
        self.kernel.registry.get_config("primary-mock").simulate_429 = True

        res = self.kernel.execute("Create file hello.py")
        self.assertEqual(res.status, "failover_success")
        self.assertEqual(res.model_used, "fallback-mock")
        self.assertTrue(len(res.handoff_notes) > 0)
        self.assertIn("Rate Limit", res.handoff_notes[0])

        # Verify recent history has temporal continuity
        history = res.updated_snapshot.recent_history
        self.assertTrue(len(history) >= 2)
        self.assertEqual(history[-2].role, "user")
        self.assertEqual(history[-1].role, "assistant")
        self.assertEqual(history[-1].model_name, "fallback-mock")


if __name__ == "__main__":
    unittest.main()
