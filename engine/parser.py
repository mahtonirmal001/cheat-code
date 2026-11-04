"""
parser.py — turns teacher-friendly text into Blocks.

Two dialects, auto-detected per line:

A) SYMBOL MODE (the user's own PDF style)
   ★ Topic heading
   ► Sub-topic heading            (auto-numbered: 1.1, 1.2 ...)
   ◆ **Label:** description       bullet
     • nested point               nested bullet
   + Solved Example / Example N
   | a | b |                      tables (with --- header separator)
   --- or [[PAGEBREAK]]           manual page break

B) MD MODE (markdown-like directives)
   # H1 / ## H2 / ### H3
   - bullet / * bullet / 1. numbered bullet
   ::: keypoint Title ... :::
   ::: example ... :::
   [eq] \\frac{a}{b} [/eq]
   [img src="x.svg" width="70%"] caption [/img]
   [q 1 marks=2] ... options A) ... [/q]
   [toc] [pagebreak]

Both can be mixed in one document.
"""

import re
import uuid
from . import model as M

SYMBOL_HEADINGS = ["★", "►", "❖", "■"]
BULLETS = ["◆", "•", "◦", "-", "▪", "‣"]


def _id():
    return "b" + uuid.uuid4().hex[:8]


def _detect_header(lines):
    """Markdown-style pipe table: second row is ---/|---|."""
    if len(lines) < 2:
        return False
    if not lines[0].strip().startswith("|"):
        return False
    return bool(re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[1])) and "-" in lines[1]


def _split_row(row):
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def parse(text, *, default_numbering=True):
    """Parse a source document into a Doc (blocks only; settings come later)."""
    doc = M.Doc()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    topic_no = 0
    sub_no = 0
    in_fence = None
    ex_count = 0

    def flush_paragraph(buf):
        if not buf:
            return
        para = " ".join(x.strip() for x in buf).strip()
        if para:
            doc.blocks.append(M.Block(type="para", text=para, id=_id(),
                                      keep=False, allow_split=True))
        buf.clear()

    para_buf = []

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # ---------------- fenced directive blocks ----------------
        if stripped.startswith(":::"):
            flush_paragraph(para_buf)
            if in_fence is None:
                head = stripped[3:].strip()
                parts = head.split(None, 1)
                kind = parts[0].lower() if parts else "note"
                title = parts[1].strip() if len(parts) > 1 else ""
                in_fence = {"kind": kind, "title": title, "body": []}
            else:
                kind = in_fence["kind"]
                body = "\n".join(in_fence["body"]).strip()
                title = in_fence["title"]
                if kind in ("example", "solved"):
                    doc.blocks.append(M.example(body, title=title or "Solved Example", id=_id()))
                else:
                    doc.blocks.append(M.box(kind, body, title=title or M.BOX_KINDS.get(kind, kind.title()), id=_id()))
                in_fence = None
            i += 1
            continue
        if in_fence is not None:
            in_fence["body"].append(raw)
            i += 1
            continue

        # ---------------- blank line ----------------
        if not stripped:
            flush_paragraph(para_buf)
            i += 1
            continue

        # ---------------- explicit directives ----------------
        m = re.match(r"^\[(pagebreak|break|newpage)\]$", stripped, re.I)
        if m:
            flush_paragraph(para_buf)
            doc.blocks.append(M.pagebreak(id=_id()))
            i += 1
            continue

        if re.match(r"^\[toc\]$", stripped, re.I):
            flush_paragraph(para_buf)
            doc.blocks.append(M.toc(id=_id()))
            i += 1
            continue

        m = re.match(r"^\[eq\](.*?)\[/eq\]$", stripped, re.I)
        if m:
            flush_paragraph(para_buf)
            doc.blocks.append(M.equation(m.group(1).strip(), id=_id()))
            i += 1
            continue

        m = re.match(r'^\[img\s+(.*?)\](.*?)\[/img\]$', stripped, re.I)
        if m:
            flush_paragraph(para_buf)
            attrs = dict(re.findall(r'(\w+)=["\']?([^"\'\s]+)["\']?', m.group(1)))
            doc.blocks.append(M.image(attrs.get("src", ""), m.group(2).strip(),
                                      width=attrs.get("width", "70%"), id=_id()))
            i += 1
            continue

        # ---------------- markdown headings ----------------
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            flush_paragraph(para_buf)
            lvl = len(m.group(1))
            txt = m.group(2).strip()
            if lvl == 1:
                topic_no += 1
                sub_no = 0
                doc.blocks.append(M.heading(txt, 1, id=_id()))
            else:
                sub_no += 1
                doc.blocks.append(M.subheading(txt, lvl - 1, id=_id(),
                                               meta={"number": "%d.%d" % (topic_no, sub_no) if topic_no else ""}))
            i += 1
            continue

        # ---------------- symbol headings ----------------
        sym = stripped[:1]
        if sym in SYMBOL_HEADINGS:
            body = stripped[1:].strip().lstrip("*").strip()
            flush_paragraph(para_buf)
            if len(body) <= 90 and not body.endswith(".") or sym == "★":
                if sym == "★":
                    topic_no += 1
                    sub_no = 0
                    doc.blocks.append(M.heading(body, 1, id=_id()))
                else:
                    sub_no += 1
                    doc.blocks.append(M.subheading(body, 1, id=_id(),
                                                   meta={"number": "%d.%d" % (max(topic_no, 1), sub_no)}))
                i += 1
                continue

        # ---------------- bullets ----------------
        bl = stripped[:1]
        if bl in BULLETS:
            flush_paragraph(para_buf)
            # nesting by indentation
            indent = len(line) - len(line.lstrip())
            body = stripped[1:].strip()
            level = 2 if indent >= 4 or stripped[:2] in ("• ", "◦ ") else 1
            doc.blocks.append(M.bullet(body, level=level, id=_id()))
            i += 1
            continue

        m = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if m and not re.match(r"^\d+\.\d", stripped):
            flush_paragraph(para_buf)
            doc.blocks.append(M.bullet(m.group(2).strip(), level=1, id=_id(),
                                       meta={"num": m.group(1)}))
            i += 1
            continue

        # ---------------- tables ----------------
        if stripped.startswith("|") or stripped.startswith("+"):
            flush_paragraph(para_buf)
            # collect a run of table lines
            tl = []
            while i < len(lines) and lines[i].strip()[:1] in ("|", "+"):
                tl.append(lines[i])
                i += 1
            has_header = len(tl) >= 2 and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", tl[1]) and "-" in tl[1]
            rows = []
            for k, row in enumerate(tl):
                if has_header and k == 1:
                    continue
                if re.match(r"^\s*\|?[\s:\-+=|]+\|?\s*$", row) and ("-" in row or "=" in row):
                    continue
                rows.append(_split_row(row))
            if rows:
                doc.blocks.append(M.table(rows, header=has_header, id=_id()))
            continue

        # ---------------- solved example header ----------------
        m = re.match(r"^(?:\+|\*\*)?\s*(solved example|example)\s*(\d+)?\s*[:.\-]?\s*(.*)$",
                     stripped, re.I)
        if m and (stripped.lower().startswith(("+", "**", "solved", "example"))):
            flush_paragraph(para_buf)
            ex_count += 1
            num = m.group(2) or str(ex_count)
            rest = m.group(3)
            body_lines = [rest] if rest else []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                s2 = nxt.strip()
                if not s2:
                    # allow blank line inside example only if next line is indented
                    if i + 1 < len(lines) and lines[i + 1].startswith(("   ", "\t")):
                        body_lines.append("")
                        i += 1
                        continue
                    break
                if s2.startswith(("►", "★", "#")):
                    break
                if nxt.startswith(("   ", "\t")) or s2.startswith(("◆", "•", "◦", "|")):
                    body_lines.append(s2)
                    i += 1
                    continue
                if re.match(r"^(?:\+|\*\*)?\s*(solved example|example)\s*\d*", s2, re.I):
                    break
                body_lines.append(s2)
                i += 1
            doc.blocks.append(M.example("\n".join(body_lines).strip(),
                                        title="Solved Example %s" % num, id=_id()))
            continue

        # ---------------- question paper items ----------------
        m = re.match(r"^(?:\[q\s*(.*?)\])?\s*Q?(\d+)[.)]\s+(.*)$", stripped, re.I)
        if m and re.match(r"^\[?(?:Q|q)?\d+[.)]", stripped):
            flush_paragraph(para_buf)
            attrs = dict(re.findall(r'(\w+)=["\']?([^"\'\s\]]+)', m.group(1) or ""))
            num = m.group(2)
            body = [m.group(3)]
            opts = []
            i += 1
            while i < len(lines):
                s2 = lines[i].strip()
                if not s2:
                    if opts or i + 1 < len(lines) and re.match(r"^\(?[A-Da-d][).]", lines[i + 1].strip()):
                        i += 1
                        continue
                    break
                om = re.match(r"^\(?([A-Da-d])[).]\s+(.*)$", s2)
                if om:
                    opts.append({"key": om.group(1).upper(), "text": om.group(2).strip()})
                    i += 1
                    continue
                if re.match(r"^\[ans\]", s2, re.I):
                    attrs["answer"] = re.sub(r"^\[ans\]\s*", "", s2, flags=re.I)
                    i += 1
                    continue
                if re.match(r"^\[?(?:Q|q)?\d+[.)]", s2):
                    break
                body.append(s2)
                i += 1
            doc.blocks.append(M.question(num, " ".join(body).strip(), options=opts,
                                         marks=attrs.get("marks"), answer=attrs.get("answer"),
                                         id=_id()))
            continue

        # ---------------- normal paragraph ----------------
        para_buf.append(stripped)
        i += 1

    flush_paragraph(para_buf)
    return doc


# --------------------------------------------------------------------------
# JSON dialect
# --------------------------------------------------------------------------
def parse_json(data):
    doc = M.Doc(title=data.get("title", "Untitled"),
                subtitle=data.get("subtitle", ""),
                author=data.get("author", ""),
                settings=data.get("settings", {}))
    for b in data.get("blocks", []):
        t = M.BLOCK_ALIASES.get(str(b.get("type", "para")).lower(), str(b.get("type", "para")).lower())
        blk = M.Block(type=t, id=b.get("id") or _id())
        for k in ("text", "level", "rows", "src", "keep", "keep_with_next", "min_lines",
                  "allow_split", "force_break", "same_page", "small", "side", "meta", "items"):
            if k in b:
                setattr(blk, k, b[k])
        if t == "box":
            blk.meta.setdefault("kind", b.get("kind", "keypoint"))
            blk.meta.setdefault("title", b.get("title") or M.BOX_KINDS.get(blk.meta["kind"], "Note"))
        doc.blocks.append(blk)
    return doc
