"""Ground-truth privacy scan. Extracts identifiers from the REAL legacy files into /tmp/qa/truth (outside the repo, never printed)
and greps the entire repo (text files + docx/xlsx/zip internals). Prints ONLY counts and file paths. usage: privacy_scan.py [legacy_dir]"""
import sys, os, re, io, json, zipfile, pathlib, collections
from openpyxl import load_workbook
LEG = sys.argv[1] if len(sys.argv) > 1 else "/root/.claude/uploads/336d2072-f701-5866-914d-4be7e75e596c"
REPO = pathlib.Path("/home/user/training")
SKIP_DIRS = {".venv", "node_modules", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}
cats = collections.defaultdict(set)
def norm_digits(s): return s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
def norm_fa(s): return s.replace("ي", "ی").replace("ك", "ک").replace("‌", " ").replace("‏", "")
def harvest_text(t):
    t = norm_digits(t)
    for m in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t): cats["email"].add(m.lower())
    for m in re.findall(r"(?<!\d)(?:0|\+98|0098)?9\d{9}(?!\d)", t): cats["mobile"].add(m[-10:])
    for m in re.findall(r"(?<!\d)\d{10}(?!\d)", t): cats["id10"].add(m)
    for m in re.findall(r"\b(?:LMS|MTC)-\d{3,9}\b", t, re.I): cats["ticket"].add(m.upper())
# 1. workbook
for p in pathlib.Path(LEG).glob("*.xlsm"):
    wb = load_workbook(p, data_only=True, read_only=True, keep_vba=False)
    for ws in wb.worksheets:
        hdr = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            vals = ["" if v is None else str(v) for v in row]
            if hdr is None and sum(1 for v in vals if v) >= 4 and i < 8: hdr = [v.strip().lower() for v in vals]
            for v in vals: harvest_text(v)
            if hdr and ws.title.lower() in ("ifs",) and i > 0:
                d = dict(zip(hdr, vals))
                fn, ln = d.get("fname", "").strip(), d.get("lname", "").strip()
                if fn and ln: cats["name_en"].add(f"{fn} {ln}".lower())
                ff, lf = d.get("farsi first name", "").strip(), d.get("farsi last name", "").strip()
                if ff and lf: cats["name_fa"].add(norm_fa(f"{ff} {lf}"))
                en = d.get("emp no", "").strip()
                if en.isdigit() and len(en) >= 5: cats["emp_no"].add(en)
                for k in ("date of birth",): pass
            if ws.title.lower() in ("chistory", "record", "payment"):
                for v in vals:
                    if re.fullmatch(r"\d{5,9}", norm_digits(v)): cats["num_id_like"].add(norm_digits(v))
# 2. documents
for p in pathlib.Path(LEG).glob("*.doc*"):
    z = zipfile.ZipFile(p)
    for n in z.namelist():
        if n.startswith("word/") and n.endswith(".xml"):
            t = re.sub(r"<[^>]+>", " ", z.read(n).decode("utf8", "ignore")); harvest_text(t)
            for m in re.findall(r"[؀-ۿ]{2,}(?: [؀-ۿ]{2,}){1,2}", norm_fa(t)): cats["fa_phrase"].add(m)
# drop generic values that are not personal (example domains, company domain, generic words)
generic_mail = re.compile(r"(irancell|mtn|example|microsoft|w3\.org|openxmlformats|schemas)", re.I)
cats["email"] = {e for e in cats["email"] if not generic_mail.search(e) or "irancell" in e and e.split("@")[0] not in ("info", "support")}
cats["email_company_domain_any"] = set()
os.makedirs("/tmp/qa/truth", exist_ok=True)
json.dump({k: sorted(v) for k, v in cats.items()}, open("/tmp/qa/truth/truth.json", "w"), ensure_ascii=False)
print("ground-truth identifier counts extracted:", {k: len(v) for k, v in cats.items() if k not in ("fa_phrase",)}, "(fa_phrase candidates:", len(cats["fa_phrase"]), ")")
# 3. scan
def texts():
    for p in REPO.rglob("*"):
        if not p.is_file() or set(p.relative_to(REPO).parts) & SKIP_DIRS: continue
        rel = str(p.relative_to(REPO)); ext = p.suffix.lower()
        try:
            if ext in (".docx", ".docm", ".xlsx", ".xlsm", ".zip", ".pptx"):
                z = zipfile.ZipFile(p)
                for n in z.namelist():
                    if n.endswith((".xml", ".rels", ".txt", ".json", ".csv")): yield f"{rel}::{n}", z.read(n).decode("utf8", "ignore")
            elif p.stat().st_size < 30_000_000:
                b = p.read_bytes()
                if b[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1") or ext in (".woff2", ".woff", ".ttf", ".ico", ".png", ".jpg", ".jpeg", ".webp", ".db", ".pyc"): continue
                yield rel, b.decode("utf8", "ignore")
        except Exception as e:
            print("unreadable:", rel, type(e).__name__)
hits = collections.defaultdict(lambda: collections.Counter())
scanned = 0
tr = {k: v for k, v in cats.items() if k in ("email", "mobile", "id10", "ticket", "name_en", "name_fa", "emp_no", "fa_phrase")}
for name, txt in texts():
    scanned += 1
    low = norm_digits(norm_fa(txt)).lower()
    for cat, vals in tr.items():
        for v in vals:
            if v.lower() in low:
                if cat == "emp_no" and not re.search(r"(?<!\d)" + re.escape(v) + r"(?!\d)", low): continue
                if cat in ("id10", "mobile") and not re.search(r"(?<!\d)" + re.escape(v) + r"(?!\d)", low): continue
                hits[(name, cat)][0] += 1
print("text/zip members scanned:", scanned)
by_cat = collections.Counter(); files = collections.defaultdict(set)
for (name, cat), c in hits.items(): by_cat[cat] += c[0]; files[cat].add(name)
print("HIT COUNTS by category (number of distinct real values found in repo):", dict(by_cat) or "none")
for cat, fs in files.items():
    print(f"  {cat}: files =", sorted(fs)[:12])
