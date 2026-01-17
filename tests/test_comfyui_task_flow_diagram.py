import os


def test_comfyui_task_flow_diagram_exists_and_has_keywords():
    project_root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(project_root, ".log", "comfyui_task_flow.txt")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "check_status" in content
    assert "SUCCEEDED" in content
    assert "FAILED" in content
    assert "PENDING" in content
    assert "queue_prompt" in content

