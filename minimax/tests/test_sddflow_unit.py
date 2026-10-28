"""Offline validation of the plumbing; DOES NOT count as real MiniMax/seekdb proof."""

import ast
import unittest

from sddflow.powercontext_client import _strings
from sddflow.runner import _functional_failure, _strip_code, _validate_candidate
from sddflow.utils import read_task, safe_source


class TestPipelineHelpers(unittest.TestCase):
    def test_required_paths_resolve_to_existing_files(self):
        task = read_task()
        for paths in task["required_sources"].values():
            for path in paths:
                self.assertTrue(safe_source(path).is_file())

    def test_code_fence_removed(self):
        self.assertEqual(_strip_code('```python\nprint(1)\n```'), 'print(1)\n')

    def test_static_model_candidate_must_preserve_signature(self):
        baseline = safe_source(read_task()["baseline_file"]).read_text()
        changed = baseline.replace('result.append(product)', 'result.append(product)\n        # scoped change')
        _validate_candidate(changed, baseline)
        broken = changed.replace('min_stock: int | None = None', 'min_stock: int | None = 1')
        with self.assertRaises(ValueError):
            _validate_candidate(broken, baseline)

    def test_detection_rejects_environment_errors(self):
        self.assertFalse(_functional_failure({"exit_code": 1,
            "stdout": "ERROR collecting tests: ModuleNotFoundError: x"}))
        self.assertTrue(_functional_failure({"exit_code": 1,
            "stdout": "1 failed\nE   assert [1, 2] == [2]"}))

    def test_state_read_scans_payload_not_local_json(self):
        found = _strings({"records": [{"content": {"text": "SDD_TASK_STATE task=inventory-min-stock-2026 | stage=validated"}}]},
                         "SDD_TASK_STATE task=inventory-min-stock-2026")
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
