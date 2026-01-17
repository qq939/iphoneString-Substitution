import unittest
from unittest.mock import patch
import sys
import os
import math

sys.path.append(os.getcwd())
import comfy_utils


class TestSegmentLengthDynamic(unittest.TestCase):
    @patch("comfy_utils.client.queue_prompt")
    def test_short_segment_reduces_length_real(self, mock_queue):
        mock_queue.return_value = ("pid", "server1")
        prompt_id, server, error = comfy_utils.queue_workflow_template(
            "character.png",
            "segment.mp4",
            workflow_type="real",
            segment_duration=1.0,
        )
        self.assertEqual(prompt_id, "pid")
        self.assertEqual(server, "server1")
        self.assertIsNone(error)
        workflow = mock_queue.call_args[0][0]
        node_a = workflow.get("232:62", {}).get("inputs", {})
        node_b = workflow.get("242:90", {}).get("inputs", {})
        self.assertIn("length", node_a)
        self.assertIn("length", node_b)
        self.assertLess(node_a["length"], 77)
        self.assertEqual(node_a["length"], node_b["length"])

    @patch("comfy_utils.client.queue_prompt")
    def test_anime_segment_length_and_filenames_v2v(self, mock_queue):
        mock_queue.return_value = ("pid_anime", "server2")
        segment_duration = 1.5
        prompt_id, server, error = comfy_utils.queue_workflow_template(
            "character_anime.png",
            "segment_anime.mp4",
            workflow_type="anime",
            segment_duration=segment_duration,
        )
        self.assertEqual(prompt_id, "pid_anime")
        self.assertEqual(server, "server2")
        self.assertIsNone(error)
        workflow = mock_queue.call_args[0][0]

        # Verify video filename is updated
        node_145 = workflow.get("145", {}).get("inputs", {})
        self.assertEqual(node_145.get("file"), "segment_anime.mp4")

        # Verify character image filename is updated (node 10 for旧工作流, 134 for v2v)
        image_found = False
        for node_id in ("10", "134"):
            node = workflow.get(node_id, {}).get("inputs", {})
            if "image" in node:
                self.assertEqual(node["image"], "character_anime.png")
                image_found = True
                break
        self.assertTrue(image_found)

        # Verify length follows 时间相等原则 for WanVaceToVideo workflow
        node_video = workflow.get("68", {}).get("inputs", {})
        fps = node_video.get("fps", 16)
        expected_length = int(math.ceil(segment_duration * fps))
        node_49 = workflow.get("49", {}).get("inputs", {})
        self.assertIn("length", node_49)
        self.assertEqual(node_49["length"], expected_length)


if __name__ == "__main__":
    unittest.main()
