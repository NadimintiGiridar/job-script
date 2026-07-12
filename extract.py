import re
import os

with open('d:/jobschelduler/web_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

match = re.search(r'DASHBOARD_HTML\s*=\s*\"\"\"(.*?)\"\"\"', content, re.DOTALL)
if match:
    with open('d:/jobschelduler/frontend.html', 'w', encoding='utf-8') as out:
        out.write(match.group(1))
    
    # Now modify web_server.py to read from the file
    new_content = content.replace(match.group(0), "import os\n\ndef get_dashboard_html():\n    with open(os.path.join(os.path.dirname(__file__), 'frontend.html'), 'r', encoding='utf-8') as f:\n        return f.read()\n\nDASHBOARD_HTML = get_dashboard_html()")
    with open('d:/jobschelduler/web_server.py', 'w', encoding='utf-8') as out:
        out.write(new_content)
    print('Successfully extracted frontend.html and updated web_server.py')
else:
    print('Could not find DASHBOARD_HTML')
