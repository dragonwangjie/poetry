#!/usr/bin/env python3
"""Validate the bundled poetry database before spending build minutes on it.

out/poetry_lite.db.gz is versioned so a fresh clone can build an APK without regenerating the
corpus. That makes it the one input CI cannot re-fetch, so it gets checked here rather than
being trusted: gzip -t only proves the deflate stream closes cleanly, and a truncated or
wrong-schema db otherwise surfaces as a ~100 second silent extraction on first launch.
"""
import gzip
import os
import sqlite3
import sys
import tempfile

MIN_POEMS = 79000


def main(path):
    size = os.path.getsize(path)
    if size < 50_000_000:
        sys.exit('%s is %d bytes -- too small to be the corpus (LFS pointer? stub?)' % (path, size))
    raw = gzip.decompress(open(path, 'rb').read())
    p = os.path.join(tempfile.mkdtemp(), 'v.db')
    with open(p, 'wb') as f:
        f.write(raw)
    con = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
    got = con.execute('pragma integrity_check').fetchone()[0]
    if got != 'ok':
        sys.exit('integrity_check said %r' % got)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    # PoemDb.java queries these by name; a db built from a different build_db.py revision would
    # be missing one and the app would only fail when the user opens a screen.
    required = {'poem', 'line', 'author', 'char_index', 'char_pos'}
    missing = required - tables
    if missing:
        sys.exit('missing tables %s (found %s)' % (sorted(missing), sorted(tables)))
    n = con.execute('select count(*) from poem').fetchone()[0]
    if n < MIN_POEMS:
        sys.exit('only %d poems in the db' % n)
    print('db ok: %d poems, %d tables, %d bytes compressed -> %d inflated'
          % (n, len(tables), size, len(raw)))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out/poetry_lite.db.gz')