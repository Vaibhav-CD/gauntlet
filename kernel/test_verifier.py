"""
Automated Test Verifier.
Runs project tests to verify that code mutations did not introduce regressions,
and captures test output for automated self-correction loops.
"""

import sys
import unittest
import io
from pathlib import Path
from typing import Tuple


class TestVerifier:
    """
    Executes tests against the current workspace state to ensure regression-free mutations.
    """

    @classmethod
    def run_tests(cls, project_root: str, test_dir: str = "tests") -> Tuple[bool, str]:
        """
        Discovers and runs unit tests in the workspace.
        Returns:
            (passed: bool, summary_output: str)
        """
        root_path = Path(project_root).resolve()
        target_tests = root_path / test_dir

        if not target_tests.exists() or not target_tests.is_dir():
            return True, f"No '{test_dir}' directory found in {project_root}. Verification skipped."

        # Ensure project root is in sys.path
        if str(root_path) not in sys.path:
            sys.path.insert(0, str(root_path))

        stream = io.StringIO()
        try:
            loader = unittest.TestLoader()
            suite = loader.discover(start_dir=str(target_tests), pattern="test_*.py")
            runner = unittest.TextTestRunner(stream=stream, verbosity=1)
            result = runner.run(suite)

            passed = result.wasSuccessful()
            output = stream.getvalue()

            summary = (
                f"Ran {result.testsRun} tests. "
                f"Errors: {len(result.errors)}, Failures: {len(result.failures)}. "
                f"{'ALL PASSED' if passed else 'TESTS FAILED'}"
            )
            return passed, f"{summary}\n\n{output}"

        except Exception as e:
            return False, f"Error discovering/running tests: {str(e)}"
