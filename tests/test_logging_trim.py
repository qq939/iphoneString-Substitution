import logging
import sys
import os

sys.path.append(os.getcwd())
import comfy_utils


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_history(self, prompt_id, server_address=None):
        # 返回包含大字段的 history，模拟真实情况
        return {
            prompt_id: {
                "outputs": {
                    "999": {
                        "images": [
                            {
                                "filename": "out.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                },
                "meta": "X" * 5000,
            }
        }

    def is_task_running(self, prompt_id, server_address=None):
        return "NOT_FOUND"


def test_check_status_log_does_not_dump_full_history(monkeypatch, caplog):
    fake_client = FakeClient()
    monkeypatch.setattr(comfy_utils, "client", fake_client)
    monkeypatch.setattr(comfy_utils, "SERVER_LIST", ["test:1"])

    with caplog.at_level(logging.INFO):
        status, result = comfy_utils.check_status("pid-123", "test:1")

    # 仍然应该返回 SUCCEEDED，并拿到文件信息
    assert status == "SUCCEEDED"
    assert isinstance(result, dict)
    assert result.get("filename") == "out.png"

    # 日志里不应该包含完整的 history JSON（例如 meta 字段）
    all_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert '"meta":' not in all_logs
