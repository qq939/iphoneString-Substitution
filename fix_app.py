
import os

file_path = "/Users/jiang/Downloads/Substitution/app.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Step 2 fix
old_step2 = 'f"【转场】已提取前一段末帧和当前段首帧，路径: {start_image_path}, {end_image_path}"'
new_step2 = 'f"【转场】步骤2/6: 首尾帧提取完成，路径: {start_image_path}, {end_image_path}"'

# Step 4 fix
old_step4 = """                        if local_path:
                            task['result_path'] = local_path
                            task['status'] = 'completed'
                        else:"""
new_step4 = """                        if local_path:
                            task['result_path'] = local_path
                            task['status'] = 'completed'
                            print(f"【转场】步骤4/6: 转场视频下载与定位完成，task_id={task['task_id']}")
                        else:"""

if old_step2 in content:
    content = content.replace(old_step2, new_step2)
    print("Replaced Step 2")
else:
    print("Step 2 not found (already replaced?)")

if old_step4 in content:
    content = content.replace(old_step4, new_step4)
    print("Replaced Step 4")
else:
    print("Step 4 not found (already replaced?)")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done writing app.py")
