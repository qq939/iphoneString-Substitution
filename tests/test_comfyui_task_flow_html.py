import os


def test_comfyui_task_flow_html_exists_and_has_keywords():
    project_root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(project_root, ".log", "comfyui_task_flow.html")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for keyword in ["check_status", "queue_prompt", "SUCCEEDED", "FAILED", "PENDING", "RUNNING"]:
        assert keyword in content

