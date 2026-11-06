_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import json
import glob
import os

for f in sorted(glob.glob(f'{_ROOT}/repo/**/*.json', recursive=True)):
    try:
        d = json.load(open(f))
    except Exception as e:
        print(os.path.basename(f), 'ERR', repr(e)[:60])
        continue
    if isinstance(d, list) and d and isinstance(d[0], dict):
        print(os.path.relpath(f, f'{_ROOT}/repo'), len(d), list(d[0].keys()))
    elif isinstance(d, dict):
        print(os.path.relpath(f, f'{_ROOT}/repo'), 'dict', list(d.keys())[:6])
    else:
        print(os.path.relpath(f, f'{_ROOT}/repo'), type(d).__name__, str(d)[:60])