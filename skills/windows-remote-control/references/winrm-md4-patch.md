# WinRM: Python MD4 Compatibility (Python 3.12+ / OpenSSL 3.0)

## Why This Is Needed

Ubuntu 24.04 / Debian 12+ ships Python 3.12 which removed MD4 from hashlib, AND OpenSSL 3.0 which disabled MD4. pywinrm's NTLM auth path (`ntlm-auth`) calls `hashlib.new('md4', ...)` which fails with `ValueError: unsupported hash type md4`.

The fix is a pure-Python MD4 implementation that monkey-patches hashlib.

## Verified Working Approach

Save the following as `/tmp/winrm_cmd2.py` on the jumpbox:

```python
import hashlib
import struct

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
        def F(x,y,z): return (x&y)|(~x&z)
        def G(x,y,z): return (x&y)|(x&z)|(y&z)
        def H(x,y,z): return x^y^z
        def lrot(x,n): return ((x<<n)|(x>>(32-n)))&0xFFFFFFFF
        # Round 1
        for i,s in [(0,3),(1,7),(2,11),(3,19),(4,3),(5,7),(6,11),(7,19),(8,3),(9,7),(10,11),(11,19),(12,3),(13,7),(14,11),(15,19)]:
            if i%4==0: A=lrot((A+F(B,C,D)+X[i])&0xFFFFFFFF,s)
            elif i%4==1: D=lrot((D+F(A,B,C)+X[i])&0xFFFFFFFF,s)
            elif i%4==2: C=lrot((C+F(D,A,B)+X[i])&0xFFFFFFFF,s)
            else: B=lrot((B+F(C,D,A)+X[i])&0xFFFFFFFF,s)
        # Round 2
        for n,i in enumerate([0,4,8,12,1,5,9,13,2,6,10,14,3,7,11,15]):
            s=[3,5,9,13][n%4]
            if n%4==0: A=lrot((A+G(B,C,D)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            elif n%4==1: D=lrot((D+G(A,B,C)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            elif n%4==2: C=lrot((C+G(D,A,B)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            else: B=lrot((B+G(C,D,A)+X[i]+0x5A827999)&0xFFFFFFFF,s)
        # Round 3
        for n,i in enumerate([0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15]):
            s=[3,9,11,15][n%4]
            if n%4==0: A=lrot((A+H(B,C,D)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            elif n%4==1: D=lrot((D+H(A,B,C)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            elif n%4==2: C=lrot((C+H(D,A,B)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            else: B=lrot((B+H(C,D,A)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
        self._A = (self._A+A)&0xFFFFFFFF; self._B = (self._B+B)&0xFFFFFFFF
        self._C = (self._C+C)&0xFFFFFFFF; self._D = (self._D+D)&0xFFFFFFFF

    def digest(self):
        buf=bytearray(self._buf); buf.append(0x80)
        while (len(buf)%64)!=56: buf.append(0x00)
        buf.extend(struct.pack('<Q',len(self._buf)*8))
        A,B,C,D=self._A,self._B,self._C,self._D
        for i in range(0,len(buf),64):
            X=list(struct.unpack('<16I',buf[i:i+64]))
            AA,BB,CC,DD=A,B,C,D
            for i,s in [(0,3),(1,7),(2,11),(3,19),(4,3),(5,7),(6,11),(7,19),(8,3),(9,7),(10,11),(11,19),(12,3),(13,7),(14,11),(15,19)]:
                F=lambda x,y,z:(x&y)|(~x&z)
                if i%4==0: A=((A+F(B,C,D)+X[i])&0xFFFFFFFF); A=((A<<s)|(A>>(32-s)))&0xFFFFFFFF
                elif i%4==1: D=((D+F(A,B,C)+X[i])&0xFFFFFFFF); D=((D<<s)|(D>>(32-s)))&0xFFFFFFFF
                elif i%4==2: C=((C+F(D,A,B)+X[i])&0xFFFFFFFF); C=((C<<s)|(C>>(32-s)))&0xFFFFFFFF
                else: B=((B+F(C,D,A)+X[i])&0xFFFFFFFF); B=((B<<s)|(B>>(32-s)))&0xFFFFFFFF
            A=(AA+A)&0xFFFFFFFF;B=(BB+B)&0xFFFFFFFF
            C=(CC+C)&0xFFFFFFFF;D=(DD+D)&0xFFFFFFFF
        return struct.pack('<4I',A,B,C,D)

original_new=hashlib.new
def patched_new(name,data=b''):
    if name.lower()=='md4':h=_MD4();h.update(data);return h
    return original_new(name,data)
hashlib.new=patched_new
```

## Usage

```python
# Load MD4 patch
exec(open('/tmp/winrm_cmd2.py').read().split("hashlib.new = patched_new")[0] + "\nhashlib.new = patched_new")
import winrm

pwd = open('/tmp/tmp-passwd').read().strip()
s = winrm.Session('192.168.71.21', auth=('chen_', pwd), transport='ntlm')
r = s.run_ps('Write-Host "WINRM_OK"')
print(r.std_out.decode('utf-8', errors='replace'))
```

## Verification

The test hash `hashlib.new('md4', b'test').digest().hex()` must equal `db346d691d7acc4dc2625db19f9e3f52`.

## Pitfalls

- Must be loaded BEFORE `import winrm` so ntlm-auth picks up the patched hashlib.
- Password must be stripped of trailing newline: `open(...).read().strip()`.
- Only needed on Python 3.12+ / systems with OpenSSL 3.0. Older systems (Python ≤3.11) have native MD4.
