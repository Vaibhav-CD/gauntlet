"""
Unit Tests for Task Tier Classification and Dynamic Routing.
"""

import unittest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from kernel.router import FailoverRouter
from kernel.models import ModelRegistry


class TestTaskTierClassification(unittest.TestCase):
    def test_tier_classification(self):
        router = FailoverRouter(ModelRegistry())

        self.assertEqual(router.classify_task_tier("Fix typo in docstring"), "fast")
        self.assertEqual(router.classify_task_tier("Please add comments to this function"), "fast")
        self.assertEqual(router.classify_task_tier("Refactor the architecture to support multi-file imports"), "reasoning")
        self.assertEqual(router.classify_task_tier("Optimize the algorithm and design pattern"), "reasoning")
        self.assertEqual(router.classify_task_tier("Implement calculate_metrics helper"), "balanced")


if __name__ == "__main__":
    unittest.main()
