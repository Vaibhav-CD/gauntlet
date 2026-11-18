"""
Unit Tests for In-Memory Syntax Validation and Security Path Traversal.
"""

import unittest
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from kernel.syntax_validator import SyntaxValidator
from kernel.state_manager import WorkspaceStateManager
from kernel.types import CodeMutation


class TestSyntaxValidator(unittest.TestCase):
    def test_valid_python(self):
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        is_valid, err = SyntaxValidator.validate("test.py", code)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_invalid_python_syntax(self):
        bad_code = "def broken(:\n    pass"
        is_valid, err = SyntaxValidator.validate("test.py", bad_code)
        self.assertFalse(is_valid)
        self.assertIn("Python SyntaxError", err)

    def test_valid_json(self):
        json_code = '{"name": "kernel", "enabled": true}'
        is_valid, err = SyntaxValidator.validate("config.json", json_code)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_invalid_json_syntax(self):
        bad_json = '{"name": "kernel", '
        is_valid, err = SyntaxValidator.validate("config.json", bad_json)
        self.assertFalse(is_valid)
        self.assertIn("JSON SyntaxError", err)

    def test_bracket_mismatch(self):
        bad_js = "function test() { const x = [1, 2; }"
        is_valid, err = SyntaxValidator.validate("script.js", bad_js)
        self.assertFalse(is_valid)


class TestStateSecurityAndValidation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="kernel_sec_")
        self.state_mgr = WorkspaceStateManager(project_root=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_path_traversal_prevention(self):
        with self.assertRaises(PermissionError):
            self.state_mgr._get_absolute_path("../../etc/passwd")

    def test_syntax_rejection_in_state_manager(self):
        mutation = CodeMutation(
            action="create",
            file_path="src/broken.py",
            content="def broken_func(a, :\n    return"
        )
        applied = self.state_mgr.apply_mutation(mutation, write_to_disk=True)
        self.assertFalse(applied.success)
        self.assertFalse(applied.syntax_valid)
        self.assertIn("Python SyntaxError", applied.error)

        # Confirm buffer and disk were not created
        self.assertNotIn("src/broken.py", self.state_mgr.snapshot.open_files)
        disk_file = Path(self.test_dir) / "src" / "broken.py"
        self.assertFalse(disk_file.exists())


if __name__ == "__main__":
    unittest.main()
