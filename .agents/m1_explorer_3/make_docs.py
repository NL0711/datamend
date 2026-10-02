# Builder for analysis.md and handoff.md
from pathlib import Path

DIR = Path(r'c:/Users/ARYAN - AYUSH/OneDrive/Desktop/skyguard/.agents/m1_explorer_3')

def append_file(filename, text):
    filepath = DIR / filename
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(text + '
')

print('make_docs.py initialized')
