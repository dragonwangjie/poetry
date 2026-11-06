#!/usr/bin/env python3
"""Convert the repo's works.npy structured array into an annotation JSON list.

works.npy is a numpy structured array with the same fields as the per-dynasty
JSON files (Title/Author/Content/Translation/Annotation/Intro/Kind/Dynasty).
Output: newline-delimited JSON with only the columns the app needs, blank rows
dropped.
"""
import json
import re
import sys

import numpy as np

TAG = re.compile(r'<[^>]+>')


def s(v):
    if isinstance(v, bytes):
        v = v.decode('utf8', 'replace')
    v = str(v if v is not None else '')
    v = TAG.sub('', v)
    v = v.replace('\r\n', '\n').replace('\r', '\n')
    v = re.sub(r'[ \t]+', ' ', v)
    v = re.sub(r'\n{2,}', '\n', v)
    return v.strip()


def main(npy_path, out_path):
    arr = np.load(npy_path, allow_pickle=False)
    print('shape', arr.shape)
    print('dtype fields', arr.dtype.names)
    names = set(arr.dtype.names or ())
    pick = lambda row, *keys: next((s(row[k]) for k in keys if k in names), '')
    n = 0
    kept = 0
    with open(out_path, 'w', encoding='utf8') as w:
        for row in arr:
            n += 1
            rec = dict(title=pick(row, 'Title', 'title'),
                       author=pick(row, 'Author', 'author'),
                       dynasty=pick(row, 'Dynasty', 'dynasty'),
                       kind=pick(row, 'Kind', 'kind'),
                       content=pick(row, 'Content', 'content'),
                       trans=pick(row, 'Translation', 'translation'),
                       note=pick(row, 'Annotation', 'annotation'),
                       intro=pick(row, 'Intro', 'intro'))
            if not (rec['trans'] or rec['note'] or rec['intro']):
                continue
            kept += 1
            w.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print('rows', n, 'kept with annotation payload', kept)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])