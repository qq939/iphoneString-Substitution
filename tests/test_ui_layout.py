import os
import sys
import re
import pytest

sys.path.append(os.getcwd())
import app

@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    with app.app.test_client() as client:
        yield client

def test_audio_generation_input_layout(client):
    """
    Test that the audio generation input (grid item 7) has the correct styling 
    to reduce top margin as requested by the user ("向上移动一点").
    """
    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    
    # We look for the input with placeholder="输入生成的文本"
    # and verify it has margin-top: 0 in its inline style.
    
    # Regex to find the input tag and capture its style attribute
    # <input type="text" name="text" placeholder="输入生成的文本" ... style="...">
    pattern = r'<input[^>]*placeholder="输入生成的文本"[^>]*style="([^"]*)"'
    
    match = re.search(pattern, html)
    assert match is not None, "Audio generation text input not found in index.html"
    
    style_content = match.group(1)
    
    # Check for margin-top: 0
    # Allow for spaces: margin-top: 0; or margin-top:0;
    assert 'margin-top: 0' in style_content or 'margin-top:0' in style_content.replace(' ', ''), \
        f"Expected 'margin-top: 0' in style attribute to move input up, but found: '{style_content}'"
