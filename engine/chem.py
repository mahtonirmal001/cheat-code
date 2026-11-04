"""
chem.py — Chemistry-aware text engine.

Turns plain teacher text into ReportLab-safe inline markup:

    "Fe3+ + SCN- -> [Fe(SCN)]2+   (blood red)"
        ->  Fe<super>3+</super> + SCN<super>-</super> → [Fe(SCN)]<super>2+</super> ...

Handles:
  * auto sub/superscript for chemical formulas  (H2O, SO4^2-, [Fe(CN)6]3-)
  * reaction arrows + conditions above/below    (-> , <=> , |> [heat] )
  * a small LaTeX subset                         ($\\mu_s=\\sqrt{n(n+2)}$)
  * markdown-ish inline markup                   (**bold**, *italic*, ==highlight==)
  * broken-font repair (mojibake "eƯective", "Nଶ", "ଷି")
  * ligature control (via CSS/theme flag, because broken ff/fi ligatures in
    the source PDF are what produce garbage glyphs upstream)
"""

import re
import html as _html

# --------------------------------------------------------------------------
# 1. GLYPH REPAIR  — the "ƯE / Nଶ / ଷି" problem
# --------------------------------------------------------------------------
# Broken subsetted fonts (very common in Indian coaching PDFs) map subscript
# digits to *wrong* codepoints from other scripts.  These are the substitutions
# observed in the user's file, plus the classic ff/fi ligature corruption.
DEFAULT_GLYPH_FIXES = {
    "\u0b36": "2",   # ଶ  (Odia letter, was subscript 2 in source font)
    "\u0b3a": "6",   # ଺  variant codepoint seen in broken subsets
    "\u0b3e": "-",
    "\u0b40": "-",
    "\u0b41": "1", "\u0b42": "2", "\u0b43": "3", "\u0b44": "4",
    "\u0b45": "5", "\u0b46": "6", "\u0b47": "7", "\u0b48": "8", "\u0b49": "9",
    "\u0b7a": "6",   # ଺  (Odia letter, was subscript 6)
    "\u0b37": "3",   # ଷ  (Odia letter, was subscript 3)
    "\u0b3f": "-",   # ି  (Odia vowel sign, was superscript minus)
    "\u0b20": "+",   # ଠ  was superscript plus
    "\u0b2c": "+",
    "\u01af": "ff",  # Ư  ligature "ff" flattened by bad encoding  (eƯective)
    "\u0192": "fi",  # ƒ
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
    "\ufb03": "ffi", "\ufb04": "ffl",
    "\u00ad": "",    # soft hyphen
    "\u200b": "",    # zero-width space that breaks copy/paste
    "\xa0": " ",
}

# characters that are suspicious inside Latin/chemical text
_SUSPICIOUS = re.compile(r"[\u0b00-\u0b7f\u0980-\u09ff\u0400-\u04ff\ufb00-\ufb06\u01af\u0192]")

# hard-coded unicode sub/superscript digits -> ASCII (so formulas can be
# re-parsed and re-formatted consistently)
_SUBS = {c: str(i) for i, c in enumerate("₀₁₂₃₄₅₆₇₈₉")}
_SUPS = {c: str(i) for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")}
_SUPS.update({"\u207a": "+", "\u207b": "-", "\u207c": "=", "\u207f": "n"})


def repair(text, fixes=None):
    """Apply glyph fixes and report anything still suspicious."""
    out = text
    table = dict(DEFAULT_GLYPH_FIXES)
    if fixes:
        table.update(fixes)
    for bad, good in table.items():
        if bad and bad in out:
            out = out.replace(bad, good)
    # normalise pre-existing unicode sub/superscripts into ^ / _ form
    out = "".join(_SUBS.get(c, c) for c in out)
    out = "".join(_SUPS.get(c, c) for c in out)
    return out


def scan_glyphs(text):
    """Return the list of suspicious characters found, with context."""
    found = {}
    for m in _SUSPICIOUS.finditer(text):
        c = m.group(0)
        ctx = text[max(0, m.start() - 12): m.end() + 12].replace("\n", " ")
        found.setdefault(c, []).append(ctx)
    return [{"char": c, "code": "U+%04X" % ord(c), "count": len(v),
             "examples": v[:3]} for c, v in found.items()]


# --------------------------------------------------------------------------
# 2. CHEMICAL FORMULA FORMATTER
# --------------------------------------------------------------------------
_ARROWS = [
    ("<==>", "⇌"), ("<=>", "⇌"), ("<->", "⇌"),
    ("-->", "→"), ("->", "→"), ("==>", "⟶"), ("=>", "⇒"),
    ("<--", "←"), ("<-", "←"),
    ("\u2192", "→"), ("\u21cc", "⇌"),
]

# words that look like formulas but are not
_STOP = {
    "A4", "B2B", "C2C", "D2D", "O2", "K12", "Q1", "Q2", "P1", "P2", "X2",
    "H1", "H2O2X", "III", "IV", "VI", "II",
}

_FORMULA_TOKEN = re.compile(
    r"""
      (?<![A-Za-z0-9_.])                   # not inside a bigger word
      (?P<coef>\d+\s*(?=[A-Z\[\(]))?       # stoichiometric coefficient: 2KClO3
      (?:
          \[[A-Za-z0-9()\[\]]+\]           # bracketed complex: [Fe(CN)6]
        | [A-Z][a-z]?                      # element
        | \([A-Za-z0-9()]+\)               # bare group
        | (?:\d+e[+\-])                    # electron: 5e-
      )
      (?: [A-Z][a-z]?
        | \([A-Za-z0-9()]*\)
        | \[[A-Za-z0-9()\[\]]*\]
        | \d+
        | [+\-]
        | ·
        | \.\d                            # hydrate dot: CuSO4.5H2O
        | \^\{?[\d+\-]*\}?
      )*
      (?![A-Za-z0-9_][a-z]?)               # not part of a bigger word
    """,
    re.X,
)

# words that look like formulas but are not
_STOP = {"A4", "B2B", "C2C", "D2D", "K12", "Q1", "Q2", "P1", "P2", "X2",
         "III", "IV", "VI", "II", "V3", "G2", "C3"}


def _element_norm(text):
    return re.sub(r"\s+", "", text)


def format_formula(f):
    """
    Format ONE formula string -> ReportLab inline markup.

        H2O             -> H<sub>2</sub>O
        SO4^2-          -> SO<sub>4</sub><super>2−</super>
        SO4 2-  (SO42-)-> SO<sub>4</sub><super>2−</super>
        [Fe(CN)6]3-     -> [Fe(CN)<sub>6</sub>]<super>3−</super>
        Fe3+            -> Fe<super>3+</super>
        CH3CH2OH        -> CH<sub>3</sub>CH<sub>2</sub>OH
        CuSO4.5H2O      -> CuSO<sub>4</sub>·5H<sub>2</sub>O
        2KClO3          -> 2KClO<sub>3</sub>
    """
    s = _element_norm(f).replace("*", "·")
    # normalise "SO4 2-" style charges written with a space or caret
    out, i, n = [], 0, len(s)
    after_dot = False

    # leading stoichiometric coefficient stays full size: 2KClO3, 8H+
    coef = re.match(r"(\d+)(?=[A-Z\[\(]|e[+\-])", s)
    if coef:
        out.append(coef.group(1))
        i = coef.end()
    while i < n:
        c = s[i]

        if c == "^":                                     # explicit superscript
            i += 1
            if i < n and s[i] == "{":
                j = s.find("}", i)
                j = n if j < 0 else j
                buf, i = s[i + 1:j], j + 1
            else:
                buf = ""
                while i < n and s[i] not in " ·":
                    buf += s[i]; i += 1
            out.append("<super>%s</super>" % _charge(buf))
            after_dot = False
            continue

        if c.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            run = s[i:j]
            if after_dot:                                # hydrate coefficient
                out.append(run); i = j; after_dot = False; continue
            # charge written inline:  Fe3+ / SO42- / [Fe(CN)6]3-
            if j < n and s[j] in "+-":
                k = j
                while k < n and s[k] in "+-":
                    k += 1
                sign = _charge(s[j:k])
                if len(run) > 1 and out and _ends_group(out):
                    # SO42-  ->  SO<sub>4</sub><super>2-</super>
                    out.append("<sub>%s</sub>" % run[:-1])
                    out.append("<super>%s%s</super>" % (run[-1], sign))
                elif len(run) > 1:
                    out.append("<sub>%s</sub><super>%s</super>" % (run[:-1], run[-1] + sign))
                else:
                    out.append("<super>%s%s</super>" % (run, sign))
                i = k
                continue
            out.append("<sub>%s</sub>" % run)
            i = j
            continue

        if c in "+-" and (i == 0 or s[i - 1] not in "+-"):   # bare charge
            j = i
            while j < n and s[j] in "+-":
                j += 1
            out.append("<super>%s</super>" % _charge(s[i:j]))
            i = j
            continue

        if c == ".":                                     # hydrate dot
            if i + 1 < n and s[i + 1].isdigit():
                out.append("·"); after_dot = True; i += 1; continue
            out.append("."); i += 1; continue

        if c == "·":
            out.append("·"); after_dot = True; i += 1; continue

        out.append(c); i += 1
        if not c.isdigit():
            after_dot = False
    return "".join(out)


def _ends_group(out):
    """True if the previous emitted piece ended with a closing bracket/element."""
    if not out:
        return False
    tail = re.sub(r"<[^>]+>", "", out[-1])
    return bool(tail) and (tail[-1].isalpha() or tail[-1] in ")]")


def _charge(s):
    return s.replace("-", "−")


# element symbols in real formulas: filter false positives
_REAL_ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si",
    "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co",
    "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I",
    "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy",
    "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au",
    "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa", "U",
    "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr", "Rf",
    "Db", "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts",
    "Og",
}


def _looks_chemical(tok):
    if tok in _STOP:
        return False
    core = re.sub(r"^\d+", "", tok)
    if re.fullmatch(r"\d+e[+\-]", core) or re.fullmatch(r"e[+\-]", core):
        return True                                    # electron
    els = re.findall(r"[A-Z][a-z]?", core)
    if not els or not any(e in _REAL_ELEMENTS for e in els):
        return False
    if not re.search(r"\d|\]|\(|\)|[A-Z][a-z]?[+\-]|·", core):
        return False
    # reject shouting abbreviations like "NCERT" / "ATP"
    letters = re.sub(r"[^A-Za-z]", "", core)
    if letters.isupper() and len(letters) > 3:
        return False
    return True


def auto_formulas(text):
    """Auto-detect formula-looking tokens in running text and format them."""
    formulas_found = []

    def repl(m):
        tok = m.group(0)
        if not _looks_chemical(tok):
            return tok
        formulas_found.append(format_formula(tok))
        return _SENTINEL_L % (len(formulas_found) - 1)
    text = _FORMULA_TOKEN.sub(repl, text)
    return re.sub(r"\x03(\d+)\x03",
                  lambda m: formulas_found[int(m.group(1))], text)


# --------------------------------------------------------------------------
# 3. mini-LaTeX  ->  markup
# --------------------------------------------------------------------------
_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι",
    "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_SYMBOLS = {
    "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "approx": "≈",
    "neq": "≠", "ne": "≠", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "infty": "∞", "sum": "Σ", "prod": "∏", "int": "∫", "partial": "∂",
    "nabla": "∇", "rightarrow": "→", "to": "→", "leftarrow": "←",
    "rightleftharpoons": "⇌", "leftrightarrow": "↔", "Rightarrow": "⇒",
    "degree": "°", "circ": "°", "ldots": "…", "dots": "…", "prime": "′",
    "parallel": "∥", "perp": "⊥", "angle": "∠", "triangle": "△",
    "propto": "∝", "in": "∈", "Delta_": "Δ", "ell": "ℓ", "hbar": "ℏ",
    "quad": "\u2003", "qquad": "\u2003\u2003", ",": "\u2009", ";": "\u2009",
}


def _read_group(s, i):
    """read {..} at position i (i points at '{') -> (content, next_index)"""
    if i >= len(s) or s[i] != "{":
        # single token
        j = i
        while j < len(s) and not s[j].isspace() and s[j] not in "}_^":
            j += 1
        return s[i:j], j
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def latex_to_markup(src):
    """Small LaTeX subset -> ReportLab inline markup (sub/sup/italic)."""
    s = src

    # \frac{a}{b} -> (a)/(b)  with a real stacked look for simple cases
    def frac_repl(m):
        a, b = m.group(1), m.group(2)
        a, b = latex_to_markup(a), latex_to_markup(b)
        return "%s⁄%s" % (a, b)
    s = re.sub(r"\\[dt]?frac\s*\{", r"\\frac{", s)
    for _ in range(4):
        s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", frac_repl, s)

    # \sqrt{x}
    s = re.sub(r"\\sqrt\{([^{}]*)\}", lambda m: "√(%s)" % latex_to_markup(m.group(1)), s)
    s = re.sub(r"\\sqrt\s*([A-Za-z0-9])", lambda m: "√" + m.group(1), s)

    # \text{...}
    s = re.sub(r"\\text\{([^{}]*)\}", lambda m: m.group(1), s)
    s = re.sub(r"\\mathrm\{([^{}]*)\}", lambda m: m.group(1), s)
    s = re.sub(r"\\mathbf\{([^{}]*)\}", lambda m: "<b>%s</b>" % m.group(1), s)
    s = re.sub(r"\\ce\{([^{}]*)\}", lambda m: m.group(1), s)

    # greek / symbols
    def sym(m):
        name = m.group(1)
        return _GREEK.get(name) or _SYMBOLS.get(name) or name
    s = re.sub(r"\\([A-Za-z]+|[,;])", sym, s)

    # superscripts / subscripts
    for _ in range(3):
        s = re.sub(r"\^\{([^{}]*)\}", lambda m: "<super>%s</super>" % m.group(1), s)
        s = re.sub(r"_\{([^{}]*)\}", lambda m: "<sub>%s</sub>" % m.group(1), s)
        s = re.sub(r"\^([A-Za-z0-9+\-])", lambda m: "<super>%s</super>" % m.group(1), s)
        s = re.sub(r"_([A-Za-z0-9+\-])", lambda m: "<sub>%s</sub>" % m.group(1), s)

    if "\\" in s:                       # leftover commands: drop the slash
        s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    return s


# --------------------------------------------------------------------------
# 4. INLINE MARKUP  ->  reportlab markup
# --------------------------------------------------------------------------
_SENTINEL_L = "\x03%d\x03"          # auto-formatted formula (post-escape)
_CHEM_RE = re.compile(r"\\(?:ce|chem)\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")


def inline(text, *, chem=True, formulas=True, math=True, keep_case=True):
    """
    Full inline pipeline.  Returns ReportLab paragraph markup.
    Order matters: protect code-ish spans -> repair -> latex -> chem -> escape
    -> markup -> restore protected spans.
    """
    if text is None:
        return ""
    text = str(text)

    protected = []

    def protect(html_snippet):
        protected.append(html_snippet)
        return "\x00%d\x00" % (len(protected) - 1)

    # ---- 1. explicit chemistry:  \ce{[Fe(CN)6]^3-}
    def chem_repl(m):
        return protect(format_formula(m.group(1)))
    text = _CHEM_RE.sub(chem_repl, text)

    # ---- 2. explicit verbatim:  `raw text`  (no auto formatting)
    def verb_repl(m):
        return protect(_html.escape(m.group(1)))
    text = re.sub(r"`([^`]*)`", verb_repl, text)

    # ---- 3. display/inline math: $...$
    def math_repl(m):
        return protect(latex_to_markup(m.group(1)))
    if math:
        text = re.sub(r"\$\$([^$]+)\$\$", math_repl, text)
        text = re.sub(r"\$([^$]+)\$", math_repl, text)

    # ---- 4. repair broken glyphs
    text = repair(text)

    # ---- 5. explicit formula span:  ~H2SO4~
    def tilde_repl(m):
        return protect(format_formula(m.group(1)))
    if chem:
        text = re.sub(r"~([^~]+)~", tilde_repl, text)

    # ---- 6. arrows & conditions
    for a, b in _ARROWS:
        text = text.replace(a, b)

    # ---- 7. escape, then markup
    text = _html.escape(text, quote=False)

    # bold / italic / highlight
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"==(.+?)==", r'<font backColor="#fff3bf">\1</font>', text)
    text = text.replace("---", "—").replace("--", "–")

    # ---- 8. auto chemical formulas (run on escaped text, formula output is
    #         pure markup so escaping-again is avoided via sentinels)
    if chem and formulas:
        text = auto_formulas(text)

    # ---- 9. restore protected spans
    def unprotect(m):
        return protected[int(m.group(1))]
    text = re.sub(r"\x00(\d+)\x00", unprotect, text)
    return text
