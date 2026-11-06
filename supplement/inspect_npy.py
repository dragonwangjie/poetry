"""Inspect the object-array works.npy: element type, keys, and payload fill by sampling."""
import collections
import random

import numpy as np

w = np.load('/root/anno/works.npy', allow_pickle=True)
print('shape', w.shape, 'dtype', w.dtype)
el = w[0]
print('element type:', type(el))
if isinstance(el, dict):
    print('keys:', list(el.keys()))
    for k, v in el.items():
        print('   %-14s %s' % (k, str(v)[:60].replace('\n', '/')))
elif isinstance(el, (list, tuple)):
    print('len', len(el), 'items:', [str(x)[:30] for x in el])
else:
    print('raw:', str(el)[:200])

random.seed(7)
idx = random.sample(range(len(w)), 4000)
keyfill = collections.Counter()
keycount = collections.Counter()
sample = []
for i in idx:
    r = w[i]
    if not isinstance(r, dict):
        keycount['<not-dict>'] += 1
        continue
    for k, v in r.items():
        keycount[k] += 1
        if isinstance(v, str) and v.strip():
            keyfill[k] += 1
    if len(sample) < 3:
        sample.append(r)
print('\nsampled', len(idx), 'rows; keys -> non-empty/seen')
for k, n in keycount.most_common(12):
    print('   %-14s %5d/%5d' % (k, keyfill[k], n))
for s in sample[:2]:
    print('---', str(s.get('Title'))[:20], '|', str(s.get('Author'))[:10],
          '| trans:', (str(s.get('Translation')) or '')[:40])