import os
import re

EXCLUDE_DIRS = {'.git', 'node_modules', 'dist', 'res', '__pycache__', '.vscode'}
EXCLUDE_PATHS = ('usecases/wa-summarizer/references',)
EXCLUDE_FILES = {'setup.py', 'licenses.txt', 'NOTICE', '_rename2.py', 'package-lock.json'}
EXTS = ('.md', '.py', '.html', '.jsx', '.js', '.json', '.sh', '.yml', '.yaml', '.txt')
PATTERNS = [
    (re.compile(r'AWS Service Screener V2'), 'Quadra Recon'),
    (re.compile(r'AWS Service Screener'), 'Quadra Recon'),
    (re.compile(r'Service Screener V2'), 'Quadra Recon'),
    (re.compile(r'Service Screener'), 'Quadra Recon'),
]

files = hits_total = 0
for root, dirs, fs in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
    if any(p in root.replace('\\', '/') for p in EXCLUDE_PATHS):
        continue
    for f in fs:
        if f in EXCLUDE_FILES or not f.endswith(EXTS):
            continue
        path = os.path.join(root, f)
        try:
            text = open(path, encoding='utf-8', newline='').read()
        except (UnicodeDecodeError, OSError):
            continue
        new, hits = text, 0
        for pat, repl in PATTERNS:
            new, n = pat.subn(repl, new)
            hits += n
        if hits:
            open(path, 'w', encoding='utf-8', newline='').write(new)
            files += 1
            hits_total += hits
print(hits_total, 'replacements in', files, 'files')
