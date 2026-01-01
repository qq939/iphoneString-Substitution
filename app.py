from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)
SUBSTITUTION_FILE = 'substitution.txt'

def get_substitutions():
    if not os.path.exists(SUBSTITUTION_FILE):
        return ""
    with open(SUBSTITUTION_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def save_substitution(char):
    with open(SUBSTITUTION_FILE, 'a', encoding='utf-8') as f:
        f.write(char)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        text = request.form.get('text')
        if text:
            # 取第一个字符
            char = text[0]
            save_substitution(char)
        return redirect(url_for('index'))
    
    substitutions = get_substitutions()
    return render_template('index.html', substitutions=substitutions)

if __name__ == '__main__':
    app.run(debug=True, port=5015)
