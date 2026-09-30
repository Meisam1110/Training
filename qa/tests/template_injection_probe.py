"""Does a data value containing {{placeholders}} get interpreted? Direct renderer call with the shipped templates."""
import sys, io, zipfile, re
sys.path.insert(0, "/home/user/training/backend")
from app.documents.renderer import DocxLetterRenderer
r = DocxLetterRenderer("/home/user/training/templates")
base = dict(Letter_No="LN-1", date="1405/07/08", To="Inst", Course_Name="C", Jstart_Date="1405/01/01", Days="d", Time="t", Duration="8", Method="m",
            company_economic_code="e", company_national_id="n", company_postal_code="p", company_address="a")
def text(res):
    z = zipfile.ZipFile(io.BytesIO(res.docx_bytes)); x = z.read("word/document.xml").decode()
    return re.sub(r"<[^>]+>", "", x)
for label, name in (("scalar->{{Letter_No}}", "{{Letter_No}}"), ("item ->{{participants.email}}", "{{participants.email}}"), ("name {{Fname}}", "{{Fname}}"), ("plain", "Ali")):
    f = dict(base, participants=[{"name": name, "national_id": "1", "phone": "2", "email": "x@example.test"}])
    try:
        res = r.render("institute_letter", f, "fa"); t = text(res)
        print(f"{label:30s} rendered; 'LN-1' occurs {t.count('LN-1')}x; 'x@example.test' {t.count('x@example.test')}x; literal '{{{{' present: {'{{' in t}")
    except Exception as e:
        print(f"{label:30s} EXC {type(e).__name__}: {str(e)[:100]}")
# scalar field containing a placeholder of another field
f = dict(base, Course_Name="{{To}} / {{Letter_No}}", participants=[{"name": "A", "national_id": "1", "phone": "2", "email": "e@example.test"}])
try:
    t = text(r.render("institute_letter", f, "fa")); print("Course_Name='{{To}} / {{Letter_No}}' ->", "Inst / LN-1" in t or (t.count("LN-1") > 1), "| literal braces left:", "{{" in t)
except Exception as e: print("Course_Name injection EXC", type(e).__name__, str(e)[:100])
