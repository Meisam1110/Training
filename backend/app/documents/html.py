"""E-mail HTML body: clean, table-based, inline-styled, RTL-aware (Outlook-safe: no CSS classes, no
flex/grid, no external images or scripts). Built from the same wording blocks as the .docx templates.
Every substituted value is HTML-escaped; only http(s) URLs become links."""
from __future__ import annotations

import re
from html import escape
from typing import Mapping, Sequence

from .engine import PLACEHOLDER, apply_filter, clean_text

FONT = "Tahoma,Arial,sans-serif"
YELLOW, BLUE, GREY = "#FFCB05", "#004A8F", "#BFBFBF"
_URL = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)


def _sub(tmpl: str, values: Mapping[str, str], persian: bool, item: Mapping[str, str] | None = None,
         list_name: str = "", idx: int = 0) -> str:
    def rep(m: re.Match) -> str:
        name, flt = m.group(1), m.group(2)
        if "." in name:
            ln, fld = name.split(".", 1)
            if ln != list_name or item is None:
                raise KeyError(name)
            v = str(idx) if fld == "_n" else item.get(fld, "")
        else:
            v = values[name]
        v = clean_text(str(v))
        v = apply_filter(v, flt, persian)
        return escape(v, quote=True)

    # escape literal text of the template too (it contains « » and quotes only, but be safe)
    out, pos = [], 0
    for m in PLACEHOLDER.finditer(tmpl):
        out.append(escape(tmpl[pos:m.start()], quote=False))
        out.append(rep(m))
        pos = m.end()
    out.append(escape(tmpl[pos:], quote=False))
    return "".join(out)


def _raw_value(tmpl: str, values: Mapping[str, str]) -> str:
    m = PLACEHOLDER.fullmatch(tmpl.strip())
    return values.get(m.group(1), "") if m else tmpl


def section_html(blocks: Sequence[tuple], values: Mapping[str, str], lists: Mapping[str, list[Mapping[str, str]]],
                 rtl: bool, persian: bool) -> str:
    d = "rtl" if rtl else "ltr"
    al = "right" if rtl else "left"
    base = f"font-family:{FONT};font-size:14px;line-height:1.7;color:#222222;direction:{d};text-align:{al};"
    rows: list[str] = []

    def row(inner: str, pad="0 0 12px 0") -> None:
        rows.append(f'<tr><td dir="{d}" align="{al}" style="{base}padding:{pad};">{inner}</td></tr>')

    for b in blocks:
        k = b[0]
        if k in ("banner", "image"):
            continue
        if k == "title":
            row(f'<div style="font-size:18px;font-weight:bold;color:{BLUE};">{_sub(b[1], values, persian)}</div>')
        elif k == "p":
            row(_sub(b[1], values, persian))
        elif k == "note":
            row(f'<span style="font-size:12px;font-style:italic;color:#555555;">{_sub(b[1], values, persian)}</span>')
        elif k == "link":
            url = _raw_value(b[2], values).strip()
            label = _sub(b[1], values, persian)
            if _URL.match(url):
                row(f'<a href="{escape(url, quote=True)}" style="color:#0563C1;text-decoration:underline;">'
                    f'{label if b[1] != b[2] else escape(url)}</a>')
            else:
                row(label if b[1] != b[2] else escape(url))
        elif k == "bullets":
            lis = "".join(f'<li style="margin:0 0 6px 0;">{_sub(t, values, persian)}</li>' for t in b[1])
            row(f'<ul dir="{d}" style="margin:0;padding:0 22px 0 22px;">{lis}</ul>')
        elif k == "meta":
            row("<br>".join(f"{escape(lbl)}: {_sub(v, values, persian)}" for lbl, v in b[1]))
        elif k == "kv":
            trs = "".join(
                f'<tr><td width="30%" bgcolor="{YELLOW}" dir="{d}" align="{al}" style="{base}font-weight:bold;'
                f'border:1px solid {GREY};padding:6px 10px;">{escape(lbl)}</td>'
                f'<td dir="{d}" align="{al}" style="{base}border:1px solid {GREY};padding:6px 10px;">'
                f'{_sub(v, values, persian)}</td></tr>' for lbl, v in b[1])
            row(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                f'style="border-collapse:collapse;">{trs}</table>')
        elif k == "grid":
            lname, cols = b[1], b[2]
            head = "".join(f'<th bgcolor="{YELLOW}" dir="{d}" align="{al}" style="{base}font-weight:bold;'
                           f'border:1px solid {GREY};padding:6px 10px;">{escape(h)}</th>' for h, _ in cols)
            body = ""
            for i, item in enumerate(lists.get(lname, []), start=1):
                tds = ""
                for _, cell in cols:
                    txt = _sub(cell, values, persian, item, lname, i)
                    plain = item.get(cell.strip()[2 + len(lname) + 1:-2]) if cell.strip().startswith("{{" + lname + ".") else ""
                    if plain and _URL.match(plain.strip()):
                        txt = f'<a href="{escape(plain.strip(), quote=True)}" style="color:#0563C1;">{txt}</a>'
                    tds += (f'<td dir="{d}" align="{al}" style="{base}font-size:13px;border:1px solid {GREY};'
                            f'padding:6px 10px;">{txt}</td>')
                body += f"<tr>{tds}</tr>"
            row(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                f'style="border-collapse:collapse;"><tr>{head}</tr>{body}</table>')
        elif k == "sign":
            lines = [_sub(t, values, persian) for t in b[1]]
            lines = [x for x in lines if x.strip()]
            row("<br>".join(lines), pad="8px 0 0 0")
        else:
            raise ValueError(k)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" dir="{d}" '
            f'style="direction:{d};">{"".join(rows)}</table>')


def build_html(sections: Sequence[tuple[str, Sequence[tuple]]], values: Mapping[str, str],
               lists: Mapping[str, list[Mapping[str, str]]], persian: bool, title: str) -> str:
    inner = []
    for i, (lang, blocks) in enumerate(sections):
        if i:
            inner.append(f'<tr><td style="padding:8px 0;"><hr style="border:0;border-top:1px solid {GREY};">'
                         f"</td></tr>")
        inner.append(f'<tr><td>{section_html(blocks, values, lists, lang == "fa", persian)}</td></tr>')
    first_lang = sections[0][0]
    return (
        '<!DOCTYPE html><html lang="%s" dir="%s"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>%s</title></head>"
        '<body style="margin:0;padding:0;background-color:#F4F4F4;">'
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#F4F4F4"><tr><td align="center" style="padding:16px 8px;">'
        '<!--[if mso]><table role="presentation" width="640" align="center" cellpadding="0" cellspacing="0" '
        'border="0"><tr><td><![endif]-->'
        '<div style="max-width:640px;margin:0 auto;">'
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" bgcolor="#FFFFFF" '
        'style="width:100%%;background-color:#FFFFFF;">'
        '<tr><td height="6" bgcolor="%s" style="height:6px;line-height:6px;font-size:0;">&nbsp;</td></tr>'
        '<tr><td style="padding:16px 24px;word-break:break-word;overflow-wrap:anywhere;">'
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0">%s</table>'
        '</td></tr></table></div>'
        '<!--[if mso]></td></tr></table><![endif]-->'
        '</td></tr></table></body></html>'
    ) % (first_lang, "rtl" if first_lang == "fa" else "ltr", escape(title), YELLOW, "".join(inner))
