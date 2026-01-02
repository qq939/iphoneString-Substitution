from flask import Flask, render_template, request, redirect, url_for, Response
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
    with open(SUBSTITUTION_FILE, 'w', encoding='utf-8') as f:
        strings = f.read()
        stringset = set(strings)
        stringset.add(char)
        f.write(''.join(stringset))

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



@app.route('/replace', methods=['POST'])
def replace():
    # ========== 关键修复1：解析原始请求体，保留换行符 ==========
    # 读取原始POST数据（避免form解析过滤换行符）
    raw_data = request.data.decode('utf-8')
    # 解析URL编码的参数（text=xxx格式）
    parsed_data = urllib.parse.parse_qs(raw_data)
    # 获取text参数，保留原始换行符（取第一个值）
    text = parsed_data.get('text', [''])[0]

    # ========== 原有替换逻辑 ==========
    substitutions = get_substitutions()
    for char in substitutions:
        text = text.replace(char, '')
    print(text)
    # ========== 关键修复2：显式指定响应编码+保留换行符 ==========
    # Response返回，强制UTF-8编码，保留换行符
    return text


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5015)
