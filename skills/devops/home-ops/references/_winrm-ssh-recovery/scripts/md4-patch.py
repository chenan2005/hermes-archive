#!/usr/bin/env python3
"""Pure-Python MD4 monkey-patch for Python 3.12+ (hashlib no longer ships MD4).
Usage: exec(open('/tmp/md4-patch.py').read())  # then import winrm normally
Also available inline in this skill's SKILL.md.
"""
import hashlib, struct

class _MD4:
    def __init__(self, data=b''):
        self._buf = bytearray(data)
    def update(self, data):
        self._buf.extend(data)
    def digest(self):
        buf = bytearray(self._buf) + b'\x80'
        while len(buf) % 64 != 56:
            buf.append(0)
        buf += struct.pack('<Q', len(self._buf) * 8)
        A, B, C, D = 0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476
        def F(x,y,z): return (x&y)|(~x&z)
        def G(x,y,z): return (x&y)|(x&z)|(y&z)
        def H(x,y,z): return x^y^z
        def lrot(x,n): return ((x<<n)|(x>>(32-n)))&0xFFFFFFFF
        for blk in range(0, len(buf), 64):
            X = list(struct.unpack('<16I', buf[blk:blk+64]))
            AA, BB, CC, DD = A, B, C, D
            for i, s in [(0,3),(1,7),(2,11),(3,19),(4,3),(5,7),(6,11),(7,19),(8,3),(9,7),(10,11),(11,19),(12,3),(13,7),(14,11),(15,19)]:
                if i%4==0: A=lrot((A+F(B,C,D)+X[i])&0xFFFFFFFF,s)
                elif i%4==1: D=lrot((D+F(A,B,C)+X[i])&0xFFFFFFFF,s)
                elif i%4==2: C=lrot((C+F(D,A,B)+X[i])&0xFFFFFFFF,s)
                else: B=lrot((B+F(C,D,A)+X[i])&0xFFFFFFFF,s)
            for n in range(16):
                i, s = [0,4,8,12,1,5,9,13,2,6,10,14,3,7,11,15][n], [3,5,9,13][n%4]
                if n%4==0: A=lrot((A+G(B,C,D)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                elif n%4==1: D=lrot((D+G(A,B,C)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                elif n%4==2: C=lrot((C+G(D,A,B)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                else: B=lrot((B+G(C,D,A)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            for n in range(16):
                i, s = [0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][n], [3,9,11,15][n%4]
                if n%4==0: A=lrot((A+H(B,C,D)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                elif n%4==1: D=lrot((D+H(A,B,C)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                elif n%4==2: C=lrot((C+H(D,A,B)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                else: B=lrot((B+H(C,D,A)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            A = (AA+A)&0xFFFFFFFF; B = (BB+B)&0xFFFFFFFF
            C = (CC+C)&0xFFFFFFFF; D = (DD+D)&0xFFFFFFFF
        return struct.pack('<4I',A,B,C,D)
    def copy(self):
        return _MD4(bytes(self._buf))

_orig = hashlib.new
hashlib.new = lambda n, d=b'': _MD4(d) if n == 'md4' else _orig(n, d)
