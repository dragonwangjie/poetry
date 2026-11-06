#!/usr/bin/env python3
"""zipalign equivalent: rewrite a zip so stored entry data starts at a 4-byte boundary."""
import struct
import sys

LFH = b'PK\x03\x04'
CDH = b'PK\x01\x02'
EOCD = b'PK\x05\x06'
CDFMT = '<HHHHHHIIIHHHHHII'   # after signature: 42 bytes
LFHFMT = '<IHHHHHIIIHH'       # includes signature: 30 bytes


def entries(data):
    eocd = data.rfind(EOCD)
    if eocd < 0:
        raise SystemExit('not a zip')
    total = struct.unpack('<H', data[eocd + 10:eocd + 12])[0]
    p = struct.unpack('<I', data[eocd + 16:eocd + 20])[0]
    for _ in range(total):
        if data[p:p + 4] != CDH:
            raise SystemExit('bad central header at %d' % p)
        f = struct.unpack(CDFMT, data[p + 4:p + 46])
        nlen, elen, clen, lho = f[9], f[10], f[11], f[15]
        name = data[p + 46:p + 46 + nlen]
        comment = data[p + 46 + nlen + elen:p + 46 + nlen + elen + clen]
        lf = struct.unpack(LFHFMT, data[lho:lho + 30])
        if data[lho + 30:lho + 30 + lf[9]] != name:
            raise SystemExit('name mismatch for %r' % name)
        body = lho + 30 + lf[9] + lf[10]
        yield f, name, comment, lf, data[body:body + f[7]]
        p += 46 + nlen + elen + clen


def main(inp, outp, align=4):
    data = open(inp, 'rb').read()
    out = bytearray()
    cd = bytearray()
    count = 0
    for f, name, comment, lf, content in entries(data):
        ver, vneed, flags, method, mtime, mdate, crc, csize = f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7]
        usize, dstart, iattr, eattr = f[8], f[12], f[13], f[14]
        extra = b''
        if method == 0 and csize:
            pad = (-(len(out) + 30 + len(name))) % align
            if pad:
                extra = b'\x00' * pad
        off = len(out)
        out += struct.pack(LFHFMT, 0x04034B50, ver, flags, method, mtime, mdate,
                                 crc, len(content), usize, len(name), len(extra))
        out += name + extra + content
        cd += CDH + struct.pack(CDFMT, ver, vneed, flags, method, mtime, mdate, crc,
                                len(content), usize, len(name), 0, len(comment), dstart,
                                iattr, eattr, off)
        cd += name + comment
        count += 1
    cd_start = len(out)
    out += cd + EOCD + struct.pack('<HHHHIIH', 0, 0, count, count, len(cd), cd_start, 0)
    open(outp, 'wb').write(bytes(out))

    bad = []
    chk = open(outp, 'rb').read()
    # verification pass using the recorded local header offsets
    eocd = chk.rfind(EOCD)
    total = struct.unpack('<H', chk[eocd + 10:eocd + 12])[0]
    p = struct.unpack('<I', chk[eocd + 16:eocd + 20])[0]
    for _ in range(total):
        f = struct.unpack(CDFMT, chk[p + 4:p + 46])
        nlen, elen, clen, lho = f[9], f[10], f[11], f[15]
        name = chk[p + 46:p + 46 + nlen]
        lnlen = struct.unpack('<H', chk[lho + 26:lho + 28])[0]
        lelen = struct.unpack('<H', chk[lho + 28:lho + 30])[0]
        doff = lho + 30 + lnlen + lelen
        if f[3] == 0 and f[7] and doff % 4:
            bad.append((name, doff % 4))
        p += 46 + nlen + elen + clen
    print('aligned %s entries=%d bad=%d size=%d' % (outp, total, len(bad), len(chk)))
    for nm, m in bad:
        print('  unaligned', nm, m)
    if bad:
        raise SystemExit(1)


main(sys.argv[1], sys.argv[2])