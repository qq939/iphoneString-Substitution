import os


def test_comfyui_task_flow_html_exists_and_has_keywords():
    project_root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(project_root, ".log", "comfyui_task_flow.html")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for keyword in ["check_status", "queue_prompt", "SUCCEEDED", "FAILED", "PENDING", "RUNNING"]:
        assert keyword in content
    # 树形判读结构的标识
    assert "树形判断结构" in content
    assert 'id="check-status-tree"' in content
