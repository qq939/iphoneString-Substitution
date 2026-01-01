from flask import Flask, render_template, request, redirect, url_for
import os
import urllib

app = Flask(__name__)
SUBSTITUTION_FILE = 'langchain/substitution.txt'

def get_substitutions():
    if not os.path.exists(SUBSTITUTION_FILE):
        return ""
    with open(SUBSTITUTION_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def save_substitution(char):
    with open(SUBSTITUTION_FILE, 'a', encoding='utf-8') as f:
        f.write(char)

def remove_substitution(char):
    if not os.path.exists(SUBSTITUTION_FILE):
        return
    content = ""
    with open(SUBSTITUTION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    # 删除所有匹配的字符
    new_content = content.replace(char, '')
    with open(SUBSTITUTION_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        text = request.form.get('text')
        action = request.form.get('action')
        
        if text:
            # 取第一个字符
            char = text[0]
            if action == 'add':
                save_substitution(char)
            elif action == 'remove':
                remove_substitution(char)
        return redirect(url_for('index'))
    
    substitutions = get_substitutions()
    return render_template('index.html', substitutions=substitutions)

# 模拟你的替换规则函数（示例）
def get_substitutions():
    # 示例：要移除的特殊字符列表
    return ['!', '@', '#', '$', '%']

@app.route('/replace', methods=['POST'])
def replace():
    # 1. 显式指定请求编码为UTF-8，避免接收中文乱码
    request.charset = 'utf-8'
    # 获取参数并解码（双重保障）
    text = request.form.get('text', '', type=urllib.parse.unquote)
    
    # 2. 执行替换逻辑（你的原有代码）
    substitutions = get_substitutions()
    for char in substitutions:
        text = text.replace(char, '')
    
    # 3. 显式指定响应编码为UTF-8，解决返回中文乱码
    # 核心：Content-Type添加charset=utf-8
    return text

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5015)
