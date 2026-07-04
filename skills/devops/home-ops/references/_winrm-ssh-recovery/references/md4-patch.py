"""
Pure Python MD4 implementation — monkey-patches hashlib on Python 3.12+
Pywinrm NTLM auth needs MD4; Python 3.12 removed it; OpenSSL 3.0 also disabled it.

Usage:
    exec(open('/tmp/md4-patch.py').read())
    import winrm
    s = winrm.Session('host', auth=('user', pwd), transport='ntlm')
    ...
"""

import hashlib, struct

class _MD4:
    def __init__(self, data=b''):
        self._buf = bytearray()
        self._A = 0x67452301
        self._B = 0xefcdab89
        self._C = 0x98badcfe
        self._D = 0x10325476
        if data:
            self.update(data)

    def update(self, data):
        self._buf.extend(data)
        while len(self._buf) >= 64:
            self._compress(self._buf[:64])
            self._buf = self._buf[64:]

    def _compress(self, block):
        X = list(struct.unpack('<16I', block))
        A, B, C, D = self._A, self._B, self._C, self._D
        def F(x, y, z): return (x & y) | (~x & z)
        def G(x, y, z): return (x & y) | (x & z) | (y & z)
        def H(x, y, z): return x ^ y ^ z
        def lrot(x, n): return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF
        for i, s in [(0,3),(1,7),(2,11),(3,19),(4,3),(5,7),(6,11),(7,19),
                     (8,3),(9,7),(10,11),(11,19),(12,3),(13,7),(14,11),(15,19)]:
            if i%4==0: A=lrot((A+F(B,C,D)+X[i])&0xFFFFFFFF,s)
            elif i%4==1: D=lrot((D+F(A,B,C)+X[i])&0xFFFFFFFF,s)
            elif i%4==2: C=lrot((C+F(D,A,B)+X[i])&0xFFFFFFFF,s)
            else: B=lrot((B+F(C,D,A)+X[i])&0xFFFFFFFF,s)
        idx2 = [0,4,8,12,1,5,9,13,2,6,10,14,3,7,11,15]
        for n in range(16):
            i, s = idx2[n], [3,5,9,13][n%4]
            if n%4==0: A=lrot((A+G(B,C,D)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            elif n%4==1: D=lrot((D+G(A,B,C)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            elif n%4==2: C=lrot((C+G(D,A,B)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            else: B=lrot((B+G(C,D,A)+X[i]+0x5A827999)&0xFFFFFFFF,s)
        idx3 = [0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15]
        for n in range(16):
            i, s = idx3[n], [3,9,11,15][n%4]
            if n%4==0: A=lrot((A+H(B,C,D)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            elif n%4==1: D=lrot((D+H(A,B,C)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            elif n%4==2: C=lrot((C+H(D,A,B)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            else: B=lrot((B+H(C,D,A)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
        self._A = (self._A+A)&0xFFFFFFFF; self._B = (self._B+B)&0xFFFFFFFF
        self._C = (self._C+C)&0xFFFFFFFF; self._D = (self._D+D)&0xFFFFFFFF

    def digest(self):
        buf = bytearray(self._buf); buf.append(0x80)
        while (len(buf)%64)!=56: buf.append(0x00)
        buf.extend(struct.pack('<Q', len(self._buf)*8))
        A,B,C,D = self._A,self._B,self._C,self._D
        for i in range(0,len(buf),64):
            X=list(struct.unpack('<16I',buf[i:i+64]))
            AA,BB,CC,DD = A,B,C,D
            for i,s in [(0,3),(1,7),(2,11),(3,19),(4,3),(5,7),(6,11),(7,19),
                        (8,3),(9,7),(10,11),(11,19),(12,3),(13,7),(14,11),(15,19)]:
                if i%4==0: A=lrot((A+((B&C)|(~B&D))+X[i])&0xFFFFFFFF,s)
                elif i%4==1: D=lrot((D+((A&B)|(~A&C))+X[i])&0xFFFFFFFF,s)
                elif i%4==2: C=lrot((C+((D&A)|(~D&B))+X[i])&0xFFFFFFFF,s)
                else: B=lrot((B+((C&D)|(~C&A))+X[i])&0xFFFFFFFF,s)
            A=(AA+A)&0xFFFFFFFF; B=(BB+B)&0xFFFFFFFF
            C=(CC+C)&0xFFFFFFFF; D=(DD+D)&0xFFFFFFFF
        return struct.pack('<4I',A,B,C,D)

    def copy(self):
        return _MD4(bytes(self._buf))

# Verify: MD4("test") should be db346d691d7acc4dc2625db19f9e3f52
assert _MD4(b'test').digest().hex() == 'db346d691d7acc4dc2625db19f9e3f52', "MD4 self-test failed!"

original_new = hashlib.new
def patched_new(name, data=b''):
    if name.lower() == 'md4':
        h = _MD4()
        if data: h.update(data)
        return h
    return original_new(name, data)
hashlib.new = patched_new
