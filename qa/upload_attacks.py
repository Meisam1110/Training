"""Malicious / malformed xlsx uploads against /import/idp and /import/legacy-workbook (scratch server on 18701)."""
import io, os, sys, time, zipfile, json, resource, subprocess
from lib import Client
import synth
BASE = os.environ.get("QA_BASE", "http://127.0.0.1:18701")
PID = int(open("/tmp/qa/imp.pid").read())
a = Client(BASE); assert a.login("qaadmin", "Qa-Admin-Pass-9137!x").status_code == 200
def rss(): 
    try: return int(open(f"/proc/{PID}/status").read().split("VmRSS:")[1].split()[0]) // 1024
    except Exception: return -1
def up(data, name="x.xlsx", ep="/import/idp"):
    t = time.time(); m0 = rss()
    try:
        r = a.post(ep, files={"file": (name, data, "application/octet-stream")})
        return r.status_code, r.text[:160].replace("\n", " "), round(time.time() - t, 2), m0, rss()
    except Exception as e:
        return "EXC", repr(e)[:120], round(time.time() - t, 2), m0, rss()
synth.build_idp_only("/tmp/qa/idp_ok.xlsx"); good = open("/tmp/qa/idp_ok.xlsx", "rb").read()
def rewrite(mod):
    zi = zipfile.ZipFile(io.BytesIO(good)); out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for n in zi.namelist():
            zo.writestr(n, mod(n, zi.read(n)))
    return out.getvalue()
res = {}
print("ok file          :", up(good))
print("empty            :", up(b""))
print("PK only          :", up(b"PK\x03\x04junk"))
print("truncated zip    :", up(good[: len(good) // 2]))
print("not xlsx ext     :", up(good, "x.xlsm"))
print("path traversal fn:", up(good, "../../../../tmp/pwn.xlsx"))
print("unicode fn       :", up(good, "‮gpj.xlsx"))
print("xlsx renamed text:", up(b"a,b,c\n1,2,3\n", "x.xlsx"))
# macro-enabled workbook: add vbaProject.bin + content type
def macro(n, d):
    return d
zi = zipfile.ZipFile(io.BytesIO(good)); out = io.BytesIO()
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
    for n in zi.namelist(): zo.writestr(n, zi.read(n))
    zo.writestr("xl/vbaProject.bin", b"\xd0\xcf\x11\xe0" + b"MACRO" * 100)
print("vba inside xlsx  :", up(out.getvalue()), "(macro is never executed; ignored)")
# XXE: external entity in sharedStrings / sheet
xxe = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
def do_xxe(n, d):
    if n == "xl/sharedStrings.xml" or n.endswith("sheet1.xml"):
        s = d.decode()
        s = s.replace('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', xxe, 1) if s.startswith("<?xml") else xxe + s
        s = s.replace("Effective Communication", "&xxe;")
        return s.encode()
    return d
r = up(rewrite(do_xxe)); print("XXE file entity  :", r)
en = a.get("/enrollments", params={"q": "root:", "page_size": 5}).json(); print("   /etc/passwd content in DB?", en["total"])
lol = '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;"><!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;"><!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;"><!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;"><!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;"><!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;"><!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">]>'
def do_lol(n, d):
    if n == "xl/sharedStrings.xml":
        s = d.decode(); s = s.replace("Effective Communication", "&lol8;"); return (lol + s.split("?>", 1)[1]).encode()
    return d
print("billion laughs   :", up(rewrite(do_lol)))
# zip bomb: sheet xml expands to ~N MB from a few KB
def bomb(mb):
    zi = zipfile.ZipFile(io.BytesIO(good)); out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zo:
        for n in zi.namelist():
            d = zi.read(n)
            if n.endswith("sheet1.xml"):
                s = d.decode(); head, tail = s.split("</sheetData>")
                filler = ('<row r="9999"><c r="A9999" t="inlineStr"><is><t>x</t></is></c></row>' * 1000)
                d = (head + filler * (mb * 1024 * 1024 // len(filler)) + "</sheetData>" + tail).encode()
            zo.writestr(n, d)
    return out.getvalue()
for mb in (50, 300):
    z = bomb(mb); print(f"zip bomb {mb}MB expanded -> {len(z)//1024} KiB compressed:", up(z))
z = bomb(600)
# giant single row count via dimension lie
print("done")
