"""
mathmini.py — a small LaTeX-subset typesetter that emits HTML/CSS.

No JS at render time, so the PDF pipeline only needs one engine (WeasyPrint).
Supported: ^ _ \\frac \\dfrac \\sqrt \\text \\mathrm \\mathbf \\overline \\vec
\\sum \\int \\left( \\right) greek, operators, spacing, \\ce{...} (chemistry),
and \\begin{cases} ... \\end{cases}.
"""

import html as _html
import re

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ϵ",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "ϕ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {
    "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "div": "÷",
    "approx": "≈", "simeq": "≃", "equiv": "≡", "neq": "≠", "ne": "≠",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "ll": "≪", "gg": "≫",
    "infty": "∞", "sum": "Σ", "prod": "∏", "int": "∫", "partial": "∂",
    "nabla": "∇", "rightarrow": "→", "to": "→", "longrightarrow": "⟶",
    "leftarrow": "←", "leftrightarrow": "↔", "rightleftharpoons": "⇌",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "degree": "°", "circ": "°", "ldots": "…", "dots": "…", "cdots": "⋯",
    "prime": "′", "parallel": "∥", "perp": "⊥", "angle": "∠",
    "triangle": "△", "propto": "∝", "in": "∈", "notin": "∉", "subset": "⊂",
    "cup": "∪", "cap": "∩", "forall": "∀", "exists": "∃", "emptyset": "∅",
    "hbar": "ℏ", "ell": "ℓ", "ast": "∗", "star": "⋆", "bullet": "•",
    "uparrow": "↑", "downarrow": "↓", "langle": "⟨", "rangle": "⟩",
    "quad": "\u2003", "qquad": "\u2003\u2003", ",": "\u2009", ";": "\u2005",
    ":": "\u2005", "!": "", " ": "\u00a0", "%": "%",
    "{": "{", "}": "}", "_": "_", "#": "#", "&": "&", "$": "$",
}
BIG_OPS = {"sum", "prod", "int", "iint", "oint", "bigcup", "bigcap"}


def _esc(t):
    return _html.escape(t, quote=False)


class MathRenderer:
    def __init__(self, chem_inline=None, display=False):
        self.chem_inline = chem_inline      # callable(text) -> html, from chem.py
        self.display = display

    # ---------------- tokenizer ----------------
    def render(self, src):
        self.s = src
        self.i = 0
        return self._seq(stop=None)

    def _seq(self, stop):
        out = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if stop and c in stop:
                break
            if c == "\\":
                out.append(self._command())
            elif c == "{":
                self.i += 1
                inner = self._seq("}")
                self.i += 1
                out.append(inner)
            elif c in "^_":
                out.append(self._script())
            elif c == "&":
                self.i += 1
                out.append('<span class="m-gap"></span>')
            elif c == "~":
                self.i += 1
                out.append("\u00a0")
            elif c in " \n\t":
                self.i += 1
                out.append(" ")
            else:
                self.i += 1
                out.append(_esc(c))
        return "".join(out)

    def _group(self):
        """Read one argument group and return its HTML."""
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1
        if self.i >= len(self.s):
            return ""
        if self.s[self.i] == "{":
            self.i += 1
            inner = self._seq("}")
            self.i += 1
            return inner
        if self.s[self.i] == "\\":
            return self._command()
        c = self.s[self.i]
        self.i += 1
        return _esc(c)

    def _raw_group(self):
        """Read a raw (unrendered) argument, for \\text and \\ce."""
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1
        if self.i < len(self.s) and self.s[self.i] == "{":
            depth, j = 0, self.i
            while j < len(self.s):
                if self.s[j] == "{":
                    depth += 1
                elif self.s[j] == "}":
                    depth -= 1
                    if depth == 0:
                        raw = self.s[self.i + 1:j]
                        self.i = j + 1
                        return raw
                j += 1
            raw = self.s[self.i + 1:]
            self.i = len(self.s)
            return raw
        c = self.s[self.i:self.i + 1]
        self.i += 1
        return c

    def _command(self):
        self.i += 1                            # skip backslash
        m = re.match(r"[A-Za-z]+", self.s[self.i:])
        if not m:
            # escaped single char: \{ \} \% \, \; \! \  (space)
            ch = self.s[self.i:self.i + 1]
            self.i += 1
            return SYMBOLS.get(ch, _esc(ch))
        name = m.group(0)
        self.i += len(name)

        if name in ("frac", "dfrac", "tfrac", "cfrac"):
            num = self._group()
            den = self._group()
            cls = "m-frac m-frac-d" if name == "dfrac" else "m-frac"
            return ('<span class="%s"><span class="m-num">%s</span>'
                    '<span class="m-den">%s</span></span>' % (cls, num, den))
        if name == "sqrt":
            idx = None
            if self.i < len(self.s) and self.s[self.i] == "[":
                j = self.s.find("]", self.i)
                idx = self.s[self.i + 1:j]
                self.i = j + 1
            body = self._group()
            ix = ('<sup class="m-rootidx">%s</sup>' % self._seq_all(idx)) if idx else ""
            return '<span class="m-sqrt">%s<span class="m-radical">√</span><span class="m-radicand">%s</span></span>' % (ix, body)
        if name in ("text", "textrm", "mbox", "mathrm", "operatorname", "textnormal"):
            raw = self._raw_group()
            cls = "m-text" if name in ("text", "textrm", "mbox", "textnormal") else "m-rm"
            return '<span class="%s">%s</span>' % (cls, _esc(raw))
        if name in ("textbf", "mathbf", "bm"):
            raw = self._raw_group()
            return '<span class="m-bf">%s</span>' % _esc(raw)
        if name in ("textit", "mathit"):
            raw = self._raw_group()
            return '<span class="m-it">%s</span>' % _esc(raw)
        if name in ("ce", "chem"):
            raw = self._raw_group()
            if self.chem_inline:
                return '<span class="m-ce">%s</span>' % self.chem_inline(raw)
            return _esc(raw)
        if name == "overline":
            return '<span class="m-overline">%s</span>' % self._group()
        if name == "underline":
            return '<span class="m-underline">%s</span>' % self._group()
        if name == "vec":
            return '<span class="m-vec">%s</span>' % self._group()
        if name in ("hat", "bar", "tilde", "dot"):
            return '<span class="m-%s">%s</span>' % (name, self._group())
        if name in ("left", "right", "big", "Big", "bigg", "Bigg"):
            nxt = self.s[self.i:self.i + 1]
            if nxt == "\\":
                return self._command()
            self.i += 1
            if nxt == ".":
                return ""
            return '<span class="m-delim">%s</span>' % _esc(nxt)
        if name in BIG_OPS:
            body = SYMBOLS.get(name, name)
            return '<span class="m-bigop">%s</span>' % body
        if name in ("limits", "nolimits", "displaystyle", "textstyle"):
            return ""
        if name == "begin":
            env = self._raw_group()
            return self._environment(env)
        if name == "end":
            self._raw_group()
            return ""
        if name in ("xrightarrow", "xleftarrow", "xrightleftharpoons", "overset", "underset"):
            label = self._raw_group()
            arrow = {"xrightarrow": "→", "xleftarrow": "←",
                     "xrightleftharpoons": "⇌"}.get(name, "")
            lab = self._seq_all(label)
            if name in ("overset",):
                base = self._group()
                return ('<span class="m-stack"><span class="m-stack-top">%s</span>'
                        '<span class="m-stack-base">%s</span></span>' % (lab, base))
            if name in ("underset",):
                base = self._group()
                return ('<span class="m-stack"><span class="m-stack-base">%s</span>'
                        '<span class="m-stack-bot">%s</span></span>' % (base, lab))
            return ('<span class="m-arrow"><span class="m-stack-top">%s</span>'
                    '<span class="m-stack-base">%s</span></span>' % (lab, arrow))
        if name in GREEK:
            return '<span class="m-greek">%s</span>' % GREEK[name]
        if name in SYMBOLS:
            return '<span class="m-op">%s</span>' % SYMBOLS[name]
        if name in ("space", "thinspace", "enspace", "hspace"):
            if self.i < len(self.s) and self.s[self.i] == "{":
                self._raw_group()
            return "\u2009"
        return '<span class="m-rm">%s</span>' % _esc(name)

    def _seq_all(self, src):
        sub = MathRenderer(self.chem_inline, self.display)
        return sub.render(src or "")

    def _environment(self, env):
        """Raw-scan to \\end{env}, split into rows (\\\\ ) and cells (& )."""
        end_tok = "\\end{%s}" % env
        j = self.s.find(end_tok, self.i)
        if j < 0:
            body_raw, self.i = self.s[self.i:], len(self.s)
        else:
            body_raw, self.i = self.s[self.i:j], j + len(end_tok)
        # the body was captured before rendering; render each cell separately
        table = []
        for row in re.split(r"\\\\", body_raw):
            if not row.strip():
                continue
            table.append([self._seq_all(c) for c in row.split("&")])
        inner = "".join(
            '<div class="m-row">%s</div>' % "".join('<span class="m-cell">%s</span>' % c for c in cells)
            for cells in table)
        brace = {"cases": ("{", ""), "pmatrix": ("(", ")"), "bmatrix": ("[", "]"),
                 "vmatrix": ("|", "|")}.get(env, ("", ""))
        return ('<span class="m-array"><span class="m-brace">%s</span>'
                '<span class="m-rows">%s</span><span class="m-brace">%s</span></span>'
                % (_esc(brace[0]), inner, _esc(brace[1])))

    # ---------------- scripts ----------------
    def _script(self):
        """Handle ^ / _ including stacked sub+sup on the same base."""
        sub = sup = None
        for _ in range(2):
            if self.i < len(self.s) and self.s[self.i] in "^_":
                kind = self.s[self.i]
                self.i += 1
                if self.i < len(self.s) and self.s[self.i] == "{":
                    self.i += 1
                    val = self._seq("}")
                    self.i += 1
                elif self.i < len(self.s) and self.s[self.i] == "\\":
                    val = self._command()
                else:
                    val = _esc(self.s[self.i:self.i + 1])
                    self.i += 1
                if kind == "^":
                    sup = val
                else:
                    sub = val
        if sub is not None and sup is not None:
            return ('<span class="m-scriptpair"><span class="m-sup">%s</span>'
                    '<span class="m-sub">%s</span></span>' % (sup, sub))
        if sup is not None:
            return '<sup class="m-sup">%s</sup>' % sup
        return '<sub class="m-sub">%s</sub>' % sub


def render_math(src, chem_inline=None, display=False):
    r = MathRenderer(chem_inline=chem_inline, display=display)
    try:
        html = r.render(src)
    except Exception:
        html = _esc(src)
    cls = "math m-display" if display else "math m-inline"
    return '<span class="%s">%s</span>' % (cls, html)


MATH_CSS = r"""
.math { font-family: "Noto Serif", "Noto Sans", "DejaVu Serif", serif; font-style: italic; }
.math .m-rm, .math .m-text, .math .m-ce { font-style: normal; }
.math .m-greek { font-style: normal; }
.math .m-bf { font-weight: 700; font-style: normal; }
.math .m-inline { }
.m-display { display: block; text-align: center; margin: 5pt 0 6pt; font-size: 1.02em; }
.m-frac { display: inline-block; vertical-align: -0.52em; text-align: center;
          margin: 0 0.14em; line-height: 1.06; }
.m-frac .m-num { display: block; padding: 0 0.22em 0.06em;
          border-bottom: 0.6pt solid currentColor; }
.m-frac .m-den { display: block; padding: 0.06em 0.22em 0; }
.m-frac-d { font-size: 1.11em; }
.m-sqrt { display: inline-block; white-space: nowrap; }
.m-radical { display: inline-block; transform: scaleY(1.16); padding-right: 0.03em; font-style: normal; }
.m-radicand { border-top: 0.6pt solid currentColor; padding: 0.06em 0.12em 0 0.05em; }
.m-rootidx { font-size: 0.6em; margin-right: -0.42em; vertical-align: 0.85em; }
sup.m-sup, .m-sup { font-size: 0.68em; vertical-align: 0.58em; line-height: 0; font-style: normal; }
sub.m-sub, .m-sub { font-size: 0.68em; vertical-align: -0.28em; line-height: 0; font-style: normal; }
.m-scriptpair { display: inline-block; vertical-align: middle; text-align: left;
                font-size: 0.68em; line-height: 1.02; margin-left: 0.06em; }
.m-scriptpair .m-sup { display: block; vertical-align: baseline; font-size: 1em; }
.m-scriptpair .m-sub { display: block; vertical-align: baseline; font-size: 1em; }
.m-bigop { font-size: 1.25em; font-style: normal; vertical-align: -0.12em; }
.m-op, .m-delim { font-style: normal; }
.m-overline { border-top: 0.6pt solid currentColor; padding-top: 0.06em; }
.m-underline { border-bottom: 0.6pt solid currentColor; }
.m-vec::before { content: ""; }
.m-vec { text-decoration: none; }
.m-array { display: inline-table; vertical-align: middle; }
.m-rows { display: table-cell; padding-left: 0.25em; }
.m-row { display: block; text-align: left; line-height: 1.35; }
.m-gap { display: inline-block; width: 1.2em; }
.m-vec { position: relative; }
.m-arrow { display: inline-block; text-align: center; line-height: 1.02;
           vertical-align: -0.28em; margin: 0 0.18em; font-style: normal; }
.m-arrow .m-stack-top { display: block; font-size: 0.62em; }
.m-arrow .m-stack-base { display: block; font-style: normal; }
.m-stack { display: inline-block; text-align: center; line-height: 1.06; vertical-align: -0.2em; }
.m-stack-top { display: block; font-size: 0.66em; }
.m-stack-bot { display: block; font-size: 0.66em; }
.m-array { display: inline-table; vertical-align: middle; }
.m-brace { display: table-cell; font-size: 1.9em; font-weight: 300;
           vertical-align: middle; font-style: normal; padding: 0 0.04em; }
.m-rows { display: table-cell; vertical-align: middle; text-align: left;
          padding-left: 0.22em; }
.m-row { display: block; line-height: 1.45; white-space: nowrap; }
.m-cell { display: inline-block; min-width: 1.2em; }
"""
