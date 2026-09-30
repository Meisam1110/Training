"""Placeholder engine for .docx (python-docx + lxml only; docxtpl-style ``{{field}}`` syntax).

* Placeholders split across runs are handled; the formatting (rPr incl. bidi/rtl/cs fonts) of the run
  where the placeholder starts is kept.
* Table rows containing ``{{list.field}}`` are repeated once per item (``{{list._n}}`` = 1-based index).
* Paragraphs consisting only of an optional placeholder whose value is empty are removed.
* Language sections are delimited by marker paragraphs ``[[LANG:fa]]`` / ``[[LANG:en]]``.
* Values are inserted as plain text (never interpreted as markup); XML-illegal characters are dropped.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Callable, Iterator, Mapping

from docx import Document
from docx.oxml.ns import qn
from docx.text.run import Run

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*(?:\|\s*(fa|ltr|iso))?\s*\}\}")
LANG_MARK = re.compile(r"^\[\[LANG:(fa|en)\]\]$")
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff\ufffe\uffff]")  # XML-illegal / C0 / C1 / surrogates

Resolver = Callable[[str, str | None], "str | None"]     # (name, filter) -> text, None = unknown


_NUMERIC_RUN = re.compile(r"^[\d\u06f0-\u06f9\u0660-\u0669][\d\u06f0-\u06f9\u0660-\u0669:/.\-\u2013\s]*[\d\u06f0-\u06f9\u0660-\u0669]$")
LRE, PDF = "\u202a", "\u202c"


def apply_filter(value: str, flt: str | None, persian: bool) -> str:
    """`|fa`: Persian digits (if enabled) and left-to-right isolation of numeric runs such as
    time ranges (otherwise '10:00-16:00' is displayed reversed inside RTL text).
    `|ltr`: isolate the value as left-to-right (phones, e-mail addresses).
    `|iso`: bidi-isolate a value of unknown script so it cannot reorder its neighbours."""
    if not flt or value == "":
        return value
    if flt == "fa":
        from app.persian import to_persian_digits
        if persian:
            value = to_persian_digits(value)
        return f"{LRE}{value}{PDF}" if _NUMERIC_RUN.match(value) else value
    if flt == "iso":      # first-strong isolate: mixed-script text (e.g. Persian day names in an English line)
        return f"\u2068{value}\u2069"
    return f"{LRE}{value}{PDF}"


# Data values are inserted with their braces swapped for private-use characters so that no later pass
# (row expansion is followed by a document-wide pass) can ever re-interpret `{{...}}` found in data.
_SHIELD = str.maketrans({"{": "\ue000", "}": "\ue001"})
_UNSHIELD = str.maketrans({"\ue000": "{", "\ue001": "}"})


def shield(value: str) -> str:
    return value.translate(_SHIELD)


def unshield_document(doc) -> None:
    """Restore literal braces in all text once every substitution is finished."""
    for root in story_roots(doc):
        for t in root.iter(qn("w:t")):
            if t.text and ("\ue000" in t.text or "\ue001" in t.text):
                t.text = t.text.translate(_UNSHIELD)


def clean_text(s: str) -> str:
    return _ILLEGAL.sub("", s)


def _runs(p) -> list:
    return [r for r in p.iter(qn("w:r"))]


def _run_text(r) -> str:
    out = []
    for ch in r:
        if ch.tag == qn("w:t"):
            out.append(ch.text or "")
        elif ch.tag == qn("w:tab"):
            out.append("\t")
        elif ch.tag in (qn("w:br"), qn("w:cr")):
            out.append("\n")
    return "".join(out)


def paragraph_text(p) -> str:
    return "".join(_run_text(r) for r in _runs(p))


def all_paragraphs(root) -> Iterator[Any]:
    yield from root.iter(qn("w:p"))


def story_roots(doc) -> list:
    """Body plus every header/footer part element."""
    roots = [doc.element.body]
    for rel in doc.part.rels.values():
        if rel.reltype.endswith(("/header", "/footer")):
            roots.append(rel.target_part.element)
    return roots


def replace_in_paragraph(p, resolver: Resolver, hide_names: frozenset[str] = frozenset()) -> str:
    """Substitute placeholders in one paragraph. Returns 'remove' if the paragraph should be dropped."""
    runs = _runs(p)
    texts = [_run_text(r) for r in runs]
    full = "".join(texts)
    if "{{" not in full:
        return ""
    matches = list(PLACEHOLDER.finditer(full))
    if not matches:
        return ""
    values = []
    for m in matches:
        v = resolver(m.group(1), m.group(2))
        if v is None:
            raise KeyError(m.group(1))
        values.append(clean_text(v))
    if len(matches) == 1 and full.strip() == matches[0].group(0) and values[0] == "" \
            and matches[0].group(1) in hide_names:
        return "remove"
    starts = []
    pos = 0
    for t in texts:
        starts.append(pos)
        pos += len(t)

    def locate(offset: int) -> int:
        for i in range(len(texts) - 1, -1, -1):
            if starts[i] <= offset:
                return i
        return 0

    new = list(texts)
    for m, val in reversed(list(zip(matches, values, strict=True))):
        s, e = m.start(), m.end()
        i, j = locate(s), locate(e - 1)
        if i == j:
            new[i] = new[i][: s - starts[i]] + val + new[i][e - starts[i]:]
        else:
            new[i] = new[i][: s - starts[i]] + val
            for k in range(i + 1, j):
                new[k] = ""
            new[j] = new[j][e - starts[j]:]
    parent = p
    for r, old, txt in zip(runs, texts, new, strict=True):
        if old != txt:
            Run(r, parent).text = txt
    return ""


def _remove(el) -> None:
    el.getparent().remove(el)


def replace_everywhere(doc, resolver: Resolver, hide_names: frozenset[str] = frozenset()) -> None:
    for root in story_roots(doc):
        for p in list(all_paragraphs(root)):
            if replace_in_paragraph(p, resolver, hide_names) == "remove":
                parent = p.getparent()
                if parent.tag == qn("w:tc") and len(parent.findall(qn("w:p"))) == 1:
                    for r in _runs(p):          # keep the mandatory paragraph, just empty it
                        Run(r, p).text = ""
                else:
                    _remove(p)


def expand_rows(doc, lists: Mapping[str, list[Mapping[str, Any]]],
                item_resolver: Callable[[str, Mapping[str, Any], int], Callable[[str, str | None], str | None]]) -> None:
    """Repeat table rows that reference ``{{list.field}}``."""
    for root in story_roots(doc):
        for tr in list(root.iter(qn("w:tr"))):
            txt = "".join(paragraph_text(p) for p in tr.iter(qn("w:p")))
            names = {m.group(1).split(".")[0] for m in PLACEHOLDER.finditer(txt) if "." in m.group(1)}
            targets = [n for n in names if n in lists]
            if not targets:
                continue
            lname = targets[0]
            items = lists[lname]
            anchor = tr
            for idx, item in enumerate(items, start=1):
                clone = copy.deepcopy(tr)
                res = item_resolver(lname, item, idx)
                for p in list(clone.iter(qn("w:p"))):
                    replace_in_paragraph(p, res)
                anchor.addnext(clone)
                anchor = clone
            _remove(tr)


def filter_language(doc, lang: str) -> None:
    """Keep only the sections for *lang* ('fa', 'en' or 'both'); markers are always removed."""
    body = doc.element.body
    current = None
    for el in list(body):
        if el.tag == qn("w:p"):
            m = LANG_MARK.match(paragraph_text(el).strip())
            if m:
                current = m.group(1)
                _remove(el)
                continue
        if el.tag == qn("w:sectPr"):
            continue
        if current and lang != "both" and current != lang:
            _remove(el)


def leftover_placeholders(doc) -> list[str]:
    left = []
    for root in story_roots(doc):
        for p in all_paragraphs(root):
            t = paragraph_text(p)
            if "{{" in t or "}}" in t:
                left.extend(m.group(1) for m in PLACEHOLDER.finditer(t))
                if not PLACEHOLDER.search(t):
                    left.append("<malformed>")
    return left


def template_placeholders(doc) -> set[str]:
    names = set()
    for root in story_roots(doc):
        for p in all_paragraphs(root):
            names.update(m.group(1) for m in PLACEHOLDER.finditer(paragraph_text(p)))
    return names


def open_template(path: str):
    return Document(path)
