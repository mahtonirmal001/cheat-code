"""
model.py — the document block model.

Everything the typesetter knows about a page is a Block.  Two layers:

  Block (this file)      semantic, what the teacher wrote
  Layout (layout.py)     a *measured* fragment of a Block placed on a page

Block flags that drive keep-together / pagination:
  keep            never split across pages (default True)
  keep_with_next  glued to the following block (headings)
  min_lines       minimum lines that must stay together (widow/orphan)
  allow_split     if the block is taller than a page, permit an overflow split
  force_break     start a new page before this block
  same_page       "keep on same page as previous" manual override
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Block:
    type: str                       # heading, subheading, bullet, table, box, example,
                                    # question, image, equation, toc, pagebreak, note
    id: str = ""
    text: str = ""                  # inline text (markup allowed)
    level: int = 0
    # content
    rows: Optional[List[List[str]]] = None      # table
    items: Optional[List[Dict]] = None          # question options / sub-items
    src: str = ""                               # image / svg source
    # flags
    keep: bool = True
    keep_with_next: bool = False
    min_lines: int = 2
    allow_split: bool = True
    force_break: bool = False
    same_page: bool = False
    small: bool = False             # shrink this block by 1 step in shrink-to-fit
    side: str = ""                  # left/right for two-column manual placement
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "", [], {}, 0, False) or k in ("type", "text")}


# --------------------------------------------------------------------------
# block factories with sane defaults
# --------------------------------------------------------------------------
BOX_KINDS = {"keypoint": "Key Point", "remember": "Remember", "example": "Solved Example",
             "examtip": "Exam Tip", "note": "Note", "mnemonic": "Mnemonic",
             "misconception": "Common Mistake", "formula": "Formula"}


def heading(text, level=1, **kw):
    return Block(type="heading", text=text, level=level,
                 keep=True, keep_with_next=True, allow_split=False,
                 min_lines=kw.pop("min_lines", 2), **kw)


def subheading(text, level=2, **kw):
    return Block(type="subheading", text=text, level=level,
                 keep=True, keep_with_next=True, allow_split=False, **kw)


def bullet(text, level=1, **kw):
    return Block(type="bullet", text=text, level=level,
                 keep=False, min_lines=kw.pop("min_lines", 2),
                 allow_split=True, **kw)


def box(kind, text, **kw):
    return Block(type="box", text=text, meta={"kind": kind,
                 "title": kw.pop("title", BOX_KINDS.get(kind, kind.title()))},
                 keep=True, allow_split=False, **kw)


def example(text, **kw):
    return Block(type="example", text=text, meta={"title": kw.pop("title", "Solved Example")},
                 keep=True, allow_split=True, min_lines=3, **kw)


def table(rows, header=True, **kw):
    return Block(type="table", rows=rows, meta={"header": header},
                 keep=True, allow_split=True, **kw)


def image(src, caption="", width="70%", **kw):
    return Block(type="image", src=src, text=caption,
                 meta={"width": width}, keep=True, allow_split=False, **kw)


def equation(tex, numbered=False, **kw):
    return Block(type="equation", text=tex, meta={"numbered": numbered},
                 keep=True, allow_split=False, **kw)


def question(num, text, options=None, marks=None, answer=None, **kw):
    return Block(type="question", text=text, meta={
        "num": num, "options": options or [], "marks": marks, "answer": answer,
        "option_layout": kw.pop("option_layout", "auto"),
    }, keep=True, allow_split=True, min_lines=2, **kw)


def pagebreak(**kw):
    return Block(type="pagebreak", keep=False, force_break=True, **kw)


def toc(**kw):
    return Block(type="toc", keep=True, allow_split=True, keep_with_next=False, **kw)


# --------------------------------------------------------------------------
# document
# --------------------------------------------------------------------------
@dataclass
class Doc:
    title: str = "Untitled"
    subtitle: str = ""
    author: str = ""
    blocks: List[Block] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)

    def add(self, *blocks):
        self.blocks.extend(blocks)
        return self

    def headings(self):
        return [(i, b) for i, b in enumerate(self.blocks)
                if b.type in ("heading", "subheading")]


BLOCK_ALIASES = {
    "h1": "heading", "h2": "subheading", "h3": "subheading",
    "★": "heading", "►": "subheading", "◆": "bullet", "•": "bullet",
    "key": "box", "remember": "box", "tip": "box", "examtip": "box",
    "ex": "example", "example": "example", "solved": "example",
    "eq": "equation", "math": "equation", "img": "image", "img": "image",
    "figure": "image", "q": "question", "mcq": "question", "br": "pagebreak",
    "hr": "pagebreak", "page-break": "pagebreak", "toc": "toc",
    "note": "note", "bullets": "bullet", "li": "bullet",
}
