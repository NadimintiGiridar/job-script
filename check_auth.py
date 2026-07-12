import re

with open('d:/jobschelduler/frontend.html', 'r', encoding='utf-8') as f:
    text = f.read()

auth_script = re.search(r'function handleLogin.*?\}', text, re.DOTALL)
if auth_script:
    print('handleLogin found.')
else:
    print('handleLogin NOT found.')

if 'id="app-container"' in text:
    print('is app-container hidden?', 'display: none' in text.split('id="app-container"')[1][:50])
if 'id="auth-container"' in text:
    print('is auth-container hidden?', 'display: none' in text.split('id="auth-container"')[1][:50])
