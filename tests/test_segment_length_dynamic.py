import unittest
from unittest.mock import patch
import sys
import os

sys.path.append(os.getcwd())
import comfy_utils


class TestSegmentLengthDynamic(unittest.TestCase):
    @patch("comfy_utils.client.queue_prompt")
    def test_short_segment_reduces_length(self, mock_queue):
        mock_queue.return_value = "pid"
        result, error = comfy_utils.queue_workflow_template(
            "character.png",
            "segment.mp4",
            workflow_type="real",
            segment_duration=1.0,
        )
        self.assertEqual(result, "pid")
        self.assertIsNone(error)
        workflow = mock_queue.call_args[0][0]
        node_a = workflow.get("232:62", {}).get("inputs", {})
        node_b = workflow.get("242:90", {}).get("inputs", {})
        self.assertIn("length", node_a)
        self.assertIn("length", node_b)
        self.assertLess(node_a["length"], 77)
        self.assertEqual(node_a["length"], node_b["length"])


if __name__ == "__main__":
    unittest.main()

