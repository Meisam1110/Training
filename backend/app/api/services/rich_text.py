"""Sanitising + strict single-pass rendering of user-written rich-text templates.

* ``sanitize`` keeps ONLY an allow-list of tags/attributes. Scripts, styles, event handlers, ``javascript:`` / ``data:`` URLs,
  comments and unknown tags never survive (unknown tags are unwrapped, script-like elements are dropped WITH their content).
* ``render`` replaces field chips (``<span data-field="Fname">sample</span>``), ``{{ Fname }}`` tokens and chip links
  (``<a data-field-href="link">``) in ONE pass over the template. Values are HTML-escaped and are emitted straight to the output,
  never re-parsed: a value containing ``{{Other}}`` or ``<b>`` stays literal text (no double substitution, no HTML injection).
"""
from __future__ import annotations

import html as _html
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ul", "ol", "li", "p", "br", "a", "table", "thead", "tbody", "tr", "th", "td", "h2", "h3", "span"}
VOID = {"br"}
# elements that are dropped TOGETHER WITH their content (only non-void ones: a void tag has no end tag, so it must never open a skip)
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "svg", "math", "template", "noscript", "textarea", "title", "head",
                     "select", "option", "button", "form", "applet", "audio", "video", "canvas", "frameset"}
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_]{0,63})\s*\}\}")
SAFE_SCHEMES = {"http", "https", "mailto", "tel"}
MAX_BODY = 100_000


def safe_url(u: str) -> str | None:
    """Return the URL if it is http(s)/mailto/tel without control characters or whitespace tricks, else None."""
    u = (u or "").strip()
    if not u or len(u) > 2000 or re.search(r"[\x00-\x20\x7f]", u):
        return None
    try:
        sp = urlsplit(u)
    except ValueError:
        return None
    if sp.scheme.lower() not in SAFE_SCHEMES:
        return None
    if sp.scheme.lower() in ("http", "https") and not sp.hostname:
        return None
    return u


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, tuple)) and not v)


def _value_html(v) -> str:
    if isinstance(v, (list, tuple)):
        rows = []
        for item in v:
            cells = item.values() if isinstance(item, Mapping) else [item]
            rows.append("<tr>" + "".join(f"<td>{_html.escape(str(c))}</td>" for c in cells) + "</tr>")
        return "<table><tbody>" + "".join(rows) + "</tbody></table>"
    return _html.escape(str(v))


@dataclass
class Rendered:
    html: str
    used: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)


class _Walker(HTMLParser):
    def __init__(self, fields: Mapping | None, known: set[str] | None):
        super().__init__(convert_charrefs=True)
        self.fields, self.known = fields, known
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip = 0                 # inside a dropped element
        self.chip = 0                 # inside a rendered chip (its sample text is discarded)
        self.used: list[str] = []
        self.unknown: set[str] = set()
        self.missing: set[str] = set()

    # -- field resolution ------------------------------------------------------------------------------------------
    def _use(self, key: str) -> tuple[bool, object]:
        if key not in self.used:
            self.used.append(key)
        if self.known is not None and key not in self.known:
            self.unknown.add(key)
            return False, None
        v = self.fields.get(key) if self.fields is not None else None
        if _blank(v):
            self.missing.add(key)
            return False, None
        return True, v

    # -- attributes ----------------------------------------------------------------------------------------------------
    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> tuple[str, str | None]:
        """Returns (attribute string, chip key or None)."""
        a = {k.lower(): (v or "") for k, v in attrs}
        out: list[str] = []
        chip = None
        if a.get("dir") in ("rtl", "ltr", "auto") and tag in {"p", "h2", "h3", "li", "ul", "ol", "table", "tr", "td", "th", "span"}:
            out.append(f'dir="{a["dir"]}"')
        if tag in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if a.get(k, "").isdigit() and 1 <= int(a[k]) <= 20:
                    out.append(f'{k}="{int(a[k])}"')
        if tag == "span" and KEY_RE.match(a.get("data-field", "")):
            chip = a["data-field"]
            out.append(f'data-field="{chip}"')
        if tag == "a":
            hk = a.get("data-field-href", "")
            href = a.get("href", "")
            tok = TOKEN_RE.fullmatch(href.strip())
            if KEY_RE.match(hk) or tok:
                key = hk if KEY_RE.match(hk) else tok.group(1)
                if self.fields is None:
                    out.append(f'data-field-href="{key}"' if KEY_RE.match(hk) else f'href="{_html.escape("{{" + key + "}}")}"')
                else:
                    ok, v = self._use(key)
                    url = safe_url(str(v)) if ok else None
                    if url:
                        out.append(f'href="{_html.escape(url, quote=True)}"')
                    elif ok:
                        self.missing.add(key)            # a value that is not a safe URL counts as missing
            else:
                url = safe_url(href)
                if url:
                    out.append(f'href="{_html.escape(url, quote=True)}"')
            out.append('rel="noopener noreferrer" target="_blank"')
        return (" " + " ".join(out)) if out else "", chip

    # -- parser events -----------------------------------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip:
            if tag in DROP_WITH_CONTENT and tag not in VOID:
                self.skip += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.skip = 1
            return
        if self.chip:
            if tag == "span":
                self.chip += 1
            return
        if tag not in ALLOWED_TAGS:
            return
        attr_s, chip = self._attrs(tag, attrs)
        if tag == "span" and chip and self.fields is not None:
            ok, v = self._use(chip)
            if ok:
                self.out.append(_value_html(v))
            self.chip = 1
            return
        if tag == "br":
            self.out.append("<br>")
            return
        self.out.append(f"<{tag}{attr_s}>")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID and tag.lower() in ALLOWED_TAGS and not self.skip and not self.chip:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip:
            if tag in DROP_WITH_CONTENT:
                self.skip -= 1
            return
        if self.chip:
            if tag == "span":
                self.chip -= 1
            return
        if tag in ALLOWED_TAGS and tag not in VOID and tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if self.skip or self.chip:
            return
        if self.fields is None:
            self.out.append(_html.escape(data, quote=False))
            return
        parts = TOKEN_RE.split(data)           # [text, key, text, key, ...]: ONE pass over the template text only
        for i, part in enumerate(parts):
            if i % 2 == 0:
                self.out.append(_html.escape(part, quote=False))
            else:
                ok, v = self._use(part)
                if ok:
                    self.out.append(_value_html(v))

    def finish(self) -> str:
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def _run(html: str, fields: Mapping | None, known: set[str] | None) -> _Walker:
    w = _Walker(fields, known)
    w.feed((html or "")[:MAX_BODY * 2])
    w.close()
    return w


def sanitize(html: str) -> str:
    """Template form: allow-listed markup, chips and ``{{tokens}}`` kept."""
    return _run(html, None, None).finish()


def referenced_fields(html: str) -> list[str]:
    """Every field key a (sanitised) template references, in order of first use: chips, tokens, chip links."""
    keys: list[str] = []
    for m in re.finditer(r'data-field(?:-href)?="([A-Za-z][A-Za-z0-9_]*)"', html or ""):
        if m.group(1) not in keys:
            keys.append(m.group(1))
    plain = re.sub(r"<[^>]+>", " ", html or "")
    for m in TOKEN_RE.finditer(plain + " ".join(re.findall(r'href="(\{\{[^"]*\}\})"', html or ""))):
        if m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def render_html(html: str, fields: Mapping, known: set[str]) -> Rendered:
    w = _run(html, fields, known)
    return Rendered(w.finish(), w.used, sorted(w.unknown), sorted(w.missing))


def render_text(text: str, fields: Mapping, known: set[str]) -> tuple[str, list[str], list[str]]:
    """Plain-text form (subjects): ``{{key}}`` replaced by the value; CR/LF stripped so a value cannot inject headers."""
    unknown: set[str] = set()
    missing: set[str] = set()
    out: list[str] = []
    for i, part in enumerate(TOKEN_RE.split(text or "")):
        if i % 2 == 0:
            out.append(part)
            continue
        if part not in known:
            unknown.add(part)
            continue
        v = fields.get(part)
        if _blank(v) or isinstance(v, (list, tuple)):
            missing.add(part)
            continue
        out.append(re.sub(r"[\r\n]+", " ", str(v)))
    return "".join(out).strip()[:300], sorted(unknown), sorted(missing)
