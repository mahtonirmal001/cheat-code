import html, re, json, io, base64
from pathlib import Path
from .chem import inline
from .parser import parse, parse_json

ROOT = Path(__file__).resolve().parent.parent

def safe(t): return html.escape(str(t or ''), quote=True)

def text(t):
    return inline(str(t or '')).replace('<super>', '<sup>').replace('</super>', '</sup>').replace('\n','<br>')

def get_doc(source):
    if source.lstrip().startswith('{'):
        try: return parse_json(json.loads(source))
        except json.JSONDecodeError: pass
    # break symbols that were pasted within paragraphs, except inside math
    source = re.sub(r'(?<=\S)\s+(?=[★►◆]\s)', '\n', source)
    return parse(source)

def make_html(source, settings):
    doc=get_doc(source); title=settings.get('title') or doc.title or 'Chemistry Notes'
    if title == 'Untitled': title='Chemistry Notes'
    theme=settings.get('theme','notes'); columns=settings.get('columns') == '2'; size=max(9.0,min(12.0,float(settings.get('fontSize',10.5))))
    compact = bool(settings.get('compact')) or theme == 'cheat'
    headings=[b for b in doc.blocks if b.type=='heading']
    parts=[]; question_no=0; answers=[]
    for b in doc.blocks:
        ident=safe(b.id); typ=b.type; data=b.meta or {}; cls='block '+safe(typ)
        if b.force_break and typ!='pagebreak': cls+=' force'
        if typ != 'table' and (b.keep or typ in ('question','example','box','image')): cls+=' keep'
        if b.keep_with_next or typ in ('heading','subheading'): cls+=' with-next'
        if typ=='pagebreak': parts.append('<div class="pagebreak"></div>'); continue
        body=text(b.text)
        if typ=='heading': content=f'<h1>★ &nbsp;{body}</h1>'
        elif typ=='subheading': content=f'<h2>► &nbsp;{safe(data.get("number",""))} {body}</h2>'
        elif typ=='bullet': content=f'<div class="bullet level{b.level}"><span class="mark">{"•" if b.level>1 else "◆"}</span><div>{body}</div></div>'
        elif typ in ('box','example'):
            label=safe(data.get('title') or ('Solved Example' if typ=='example' else 'Key Point'))
            content=f'<div class="box-inner"><div class="box-title">{label}</div><div>{body}</div></div>'
        elif typ=='table':
            rows=b.rows or []; header=data.get('header',True)
            def row(r, tag): return '<tr>'+''.join(f'<{tag}>{text(c)}</{tag}>' for c in r)+ '</tr>'
            content='<table>'+('<thead>'+row(rows[0],'th')+'</thead>' if rows and header else '')+'<tbody>'+''.join(row(r,'td') for r in rows[1 if header else 0:])+'</tbody></table>'
        elif typ=='question':
            question_no+=1; num=question_no; opts=data.get('options',[]) or b.items or []
            marks=f'<span class="marks">[{safe(data["marks"])} marks]</span>' if data.get('marks') else ''
            options=''.join(f'<div>({safe(o.get("key",chr(65+i)))}) {text(o.get("text",""))}</div>' if isinstance(o,dict) else f'<div>({chr(65+i)}) {text(o)}</div>' for i,o in enumerate(opts))
            answer=data.get('answer');
            if answer: answers.append((num,answer))
            content=f'<div class="qtitle"><strong>Q{num}.</strong> {body}{marks}</div>'+ (f'<div class="options {"single" if settings.get("optionLayout")=="single" else ""}">{options}</div>' if options else '')
            if answer and settings.get('answerMode')=='inline': content+=f'<div class="answer">Answer: {text(answer)}</div>'
        elif typ=='equation':
            from .mathmini import render_math
            content=render_math(b.text,chem_inline=text,display=True)
        elif typ=='image':
            src=b.src or ''
            if src.startswith('data:image/') and len(src)<2000000:
                content=f'<figure><img src="{safe(src)}"><figcaption>{body}</figcaption></figure>'
            else: content=f'<div class="missing">Diagram: use a data:image URL in JSON. {body}</div>'
        elif typ=='toc':
            content='<h2>Contents</h2><ul class="toc-list">'+''.join(f'<li><a href="#{safe(h.id)}">{text(h.text)}</a></li>' for h in headings)+'</ul>'
        else: content=f'<p>{body}</p>'
        parts.append(f'<div id="{ident}" class="{cls}">{content}</div>')
    if answers and settings.get('answerMode')=='separate':
        parts.append('<div class="pagebreak"></div><h1>Answer Key</h1>'+''.join(f'<p><b>Q{n}.</b> {text(a)}</p>' for n,a in answers))
    fonts=''.join(f'''@font-face {{font-family: Noto; src: url("{(ROOT/'fonts'/('NotoSans-'+f+'.ttf')).as_uri()}"); font-weight:{w};}}''' for f,w in [('Regular',400),('Bold',700)])
    fonts+=f'''@font-face {{font-family: Devanagari; src: url("{(ROOT/'fonts'/'NotoSansDevanagari-Regular.ttf').as_uri()}");}} @font-face {{font-family: Devanagari;src:url("{(ROOT/'fonts'/'NotoSansDevanagari-Bold.ttf').as_uri()}");font-weight:700;}}'''
    from .mathmini import MATH_CSS
    theme_css = {'question': '.question{border-bottom:0.5pt solid #dfe7e5;padding:5pt 0 9pt}.doc-title{color:#243044}', 'worksheet': '.question{border-bottom:1pt dashed #ccd8d3;padding-bottom:14pt}.doc-title{color:#285b50}', 'cheat': 'body{font-size:9.5pt}.block{margin-bottom:3pt}h1{font-size:14pt}h2{font-size:11pt}'}.get(theme,'')
    css=f'''{fonts} {MATH_CSS} {theme_css}
    @page {{size:A4; margin:2cm; @top-left {{ content: "{safe(title).replace(chr(34),'') }"; font: 8pt Noto,Devanagari,sans-serif; color:#718096; }} @top-right {{content:"{safe(settings.get('institute','')).replace(chr(34),'')}"; font:8pt Noto,Devanagari,sans-serif; color:#718096;}} @bottom-center {{content: "Page " counter(page) " of " counter(pages); font:8pt Noto,sans-serif;color:#718096;}} }}
    * {{box-sizing:border-box}} body {{font-family:Noto,Devanagari,sans-serif;font-size:{size}pt;line-height:1.4;color:#24344a;font-variant-ligatures:none; overflow-wrap:anywhere;}} h1,h2,p {{margin:0}} .doc-title {{font-size:20pt;color:#15365c;margin:0 0 4pt;font-weight:700}} .doc-sub {{color:#698092;margin-bottom:16pt;font-size:9pt}} .block {{margin:0 0 {5 if compact else 8}pt}} .keep {{break-inside:avoid;}} .with-next {{break-after:avoid}} .force,.pagebreak {{break-before:page}} .pagebreak {{height:0}} h1 {{font-size:16pt;color:#173b68; margin:13pt 0 5pt;bookmark-level:1;break-after:avoid}} h2 {{font-size:12pt;color:#19806d; margin:9pt 0 4pt;bookmark-level:none;break-after:avoid}} p, .bullet {{orphans:3;widows:3}} .bullet {{display:flex;gap:7pt}} .mark {{color:#1a8b7a}} .level2 {{margin-left:17pt}} strong,b {{font-weight:700}} sup,sub {{font-size:70%;line-height:0}} .box-inner {{background:#edf7f5;border-left:3pt solid #28a58e;padding:9pt 11pt;border-radius:3pt;white-space:normal}} .example .box-inner {{background:#fff7e7;border-color:#e9a537}} .box-title {{font-size:9pt;color:#187963;font-weight:700;margin-bottom:4pt;text-transform:uppercase;letter-spacing:.04em}} .example .box-title {{color:#a56815}} table {{border-collapse:collapse;width:100%;font-size:9.5pt}} thead {{display:table-header-group}} tr {{break-inside:avoid}} th,td {{border:0.5pt solid #d4e0e5;padding:5pt 6pt;text-align:left;vertical-align:top}} th {{background:#e7f1f2;color:#204c55}} .qtitle {{position:relative;padding-right:40pt}} .marks {{float:right;font-size:8pt;color:#64768a}} .options {{display:block;margin:6pt 0 0 16pt}} .options > div {{display:inline-block;width:49%;vertical-align:top;padding:2pt}} .options.single > div {{display:block;width:100%}} .answer {{color:#19806d;margin-top:5pt}} figure {{margin:0;text-align:center}} img {{max-width:100%;max-height:19cm}} figcaption {{font-size:9pt;color:#708090}} .missing {{color:#b45039}} .toc-list {{padding-left:20pt}} .toc-list a {{color:#244e70;text-decoration:none}} .toc-list a::after {{content:leader('.') target-counter(attr(href), page)}} .content {{ {'column-count:2;column-gap:18pt;' if columns else ''} }}
    '''
    html_out=f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body><div class="doc-title">{safe(title)}</div><div class="doc-sub">{safe(settings.get("subtitle", "Study notes · Chemistry"))}</div><main class="content">{"".join(parts)}</main></body></html>'
    return html_out,doc

# --------------------------------------------------------------------------
# Fallback PDF rendering via ReportLab (when WeasyPrint/pango not available)
# --------------------------------------------------------------------------
try:
    from weasyprint import HTML as _WP_HTML
    from weasyprint.urls import URLFetcher as _WP_Fetcher
    _HAS_WEASY = True
except Exception:
    _HAS_WEASY = False
    _WP_HTML = None

def _can_use_weasy():
    if not _HAS_WEASY:
        return False
    # also check if pango can load - try a tiny render
    try:
        from weasyprint.text.ffi import pango  # noqa
        return True
    except Exception:
        return False

class _FallbackResult:
    def __init__(self, pdf_bytes, num_pages, headings):
        self._pdf_bytes = pdf_bytes
        self._num_pages = num_pages
        self.headings = headings
        # mimic weasyprint pages: list with length = pages, each has size
        self.pages = [object() for _ in range(num_pages)]
        # for compatibility with tests that do len(result.pages)
    def write_pdf(self):
        return self._pdf_bytes
    def make_bookmark_tree(self):
        # return something truthy if there are headings
        return self.headings or [{"label": "Document", "children": []}]

def _strip_math_html(html_snippet):
    """Strip span-heavy math HTML to plain text for reportlab fallback"""
    # remove tags but keep unicode
    t = re.sub(r'<[^>]+>', ' ', html_snippet)
    t = html.unescape(t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t or html_snippet

def _rl_safe(text_html):
    """Convert our inline HTML (with <b>, <i>, <sup>, <sub>, <font>) to reportlab-safe para XML.
       ReportLab Paragraph supports: b, i, u, super, sub, font, br, a, etc.
       We need to: 
       - replace <sup> with <super> if needed (both work, but <super> is canonical)
       - ensure entities escaped properly except tags
       - strip unsupported tags like <span>, <div>
    """
    if not text_html:
        return ""
    # we already have escaped text + allowed tags from inline()
    # Convert <sup> to <super> and </sup> to </super>
    s = text_html.replace('<sup>', '<super>').replace('</sup>', '</super>')
    # replace <br> with <br/> for XML
    s = s.replace('<br>', '<br/>')
    # remove font backColor unsupported? keep font tag but translate backColor to backcolor
    # ReportLab font supports color but not backColor in all versions; we will keep as is but fallback to color
    # Strip span, div, etc. Keep content
    s = re.sub(r'</?(span|div|figure|figcaption|a|p|strong)[^>]*>', lambda m: '<b>' if m.group(0).startswith('<strong') else ('</b>' if m.group(0).startswith('</strong') else ''), s, flags=re.I)
    # Clean double spaces but preserve tags
    # Ensure we don't have stray <font backColor> -> try to convert to highlight
    s = s.replace('backColor', 'backcolor')
    return s

def _rl_text(raw_text):
    """Take raw source text (like heading or bullet) and produce reportlab-safe string"""
    # inline will handle chem formulas, bold, etc.
    return _rl_safe(inline(raw_text))

def _build_fallback_pdf(doc, settings, markup):
    """Build PDF using ReportLab Platypus"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                     PageBreak, KeepTogether, HRFlowable, Image, ListFlowable, ListItem)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import base64 as b64
    
    buffer = io.BytesIO()
    
    # Register fonts if available
    font_regular = 'Helvetica'
    font_bold = 'Helvetica-Bold'
    font_italic = 'Helvetica-Oblique'
    # Try to register Noto
    try:
        noto_regular = ROOT / 'fonts' / 'NotoSans-Regular.ttf'
        noto_bold = ROOT / 'fonts' / 'NotoSans-Bold.ttf'
        if noto_regular.exists():
            pdfmetrics.registerFont(TTFont('Noto', str(noto_regular)))
            font_regular = 'Noto'
        if noto_bold.exists():
            pdfmetrics.registerFont(TTFont('Noto-Bold', str(noto_bold)))
            font_bold = 'Noto-Bold'
        # Also try Serif for headings
        serif_reg = ROOT / 'fonts' / 'NotoSerif-Regular.ttf'
        serif_bold = ROOT / 'fonts' / 'NotoSerif-Bold.ttf'
        if serif_reg.exists():
            pdfmetrics.registerFont(TTFont('NotoSerif', str(serif_reg)))
        if serif_bold.exists():
            pdfmetrics.registerFont(TTFont('NotoSerif-Bold', str(serif_bold)))
    except Exception:
        pass

    margin = 2*cm
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleCustom', parent=styles['Title'], fontName=font_bold, fontSize=20, textColor=colors.HexColor('#15365c'), spaceAfter=4, alignment=TA_LEFT, leading=22)
    sub_title_style = ParagraphStyle('SubTitle', parent=styles['Normal'], fontName=font_regular, fontSize=9, textColor=colors.HexColor('#698092'), spaceAfter=16, leading=11)
    h1_style = ParagraphStyle('H1', parent=styles['Heading1'], fontName=font_bold, fontSize=16, textColor=colors.HexColor('#173b68'), spaceBefore=13, spaceAfter=5, leading=18, keepWithNext=True)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontName=font_bold, fontSize=12, textColor=colors.HexColor('#19806d'), spaceBefore=9, spaceAfter=4, leading=14, keepWithNext=True)
    normal_style = ParagraphStyle('NormalCustom', parent=styles['Normal'], fontName=font_regular, fontSize=10.5, textColor=colors.HexColor('#24344a'), leading=15, spaceAfter=6, alignment=TA_LEFT, wordWrap='CJK')
    bullet_style = ParagraphStyle('Bullet', parent=normal_style, leftIndent=14, firstLineIndent=0, spaceAfter=4, bulletIndent=0)
    bullet2_style = ParagraphStyle('Bullet2', parent=bullet_style, leftIndent=28)
    box_title_style = ParagraphStyle('BoxTitle', parent=styles['Normal'], fontName=font_bold, fontSize=9, textColor=colors.HexColor('#187963'), leading=11, spaceAfter=4)
    box_body_style = ParagraphStyle('BoxBody', parent=normal_style, fontSize=9.5, leading=13, textColor=colors.HexColor('#24344a'))
    example_title_style = ParagraphStyle('ExampleTitle', parent=box_title_style, textColor=colors.HexColor('#a56815'))
    small_style = ParagraphStyle('Small', parent=normal_style, fontSize=9.5, textColor=colors.HexColor('#708090'), alignment=TA_CENTER)
    question_style = ParagraphStyle('Question', parent=normal_style, fontName=font_bold, spaceAfter=3, leading=15)
    option_style = ParagraphStyle('Option', parent=normal_style, leftIndent=16, spaceAfter=2, fontSize=10, leading=13)
    answer_style = ParagraphStyle('Answer', parent=normal_style, textColor=colors.HexColor('#19806d'), spaceBefore=5)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontName=font_regular, fontSize=8, textColor=colors.HexColor('#718096'), alignment=TA_CENTER)
    
    # Adjust for compact/cheat
    compact = bool(settings.get('compact')) or settings.get('theme') == 'cheat'
    if compact:
        for s in [normal_style, bullet_style, bullet2_style, box_body_style, option_style]:
            s.spaceAfter = 3
            s.leading = 13
        h1_style.spaceBefore = 8
        h1_style.spaceAfter = 3
        h2_style.spaceBefore = 6

    title_text = settings.get('title') or doc.title or 'Chemistry Notes'
    if title_text == 'Untitled':
        title_text = 'Chemistry Notes'
    institute = settings.get('institute', '')
    theme = settings.get('theme', 'notes')
    
    # Header/footer callback
    def _header_footer(canvas, doc_template):
        canvas.saveState()
        # Header
        canvas.setFont(font_regular, 8)
        canvas.setFillColor(colors.HexColor('#718096'))
        # top-left title
        canvas.drawString(margin, A4[1] - margin + 12, title_text[:70])
        # top-right institute
        if institute:
            canvas.drawRightString(A4[0] - margin, A4[1] - margin + 12, institute[:70])
        # Footer page numbers
        canvas.setFont(font_regular, 8)
        page_text = f"Page {doc_template.page}"
        # Note: total pages not known until end; we show current page; for 'of total' we'd need two-pass. Use simple.
        canvas.drawCentredString(A4[0]/2, margin - 14, page_text)
        # Line under header
        canvas.setStrokeColor(colors.HexColor('#e2e9e6'))
        canvas.setLineWidth(0.5)
        canvas.line(margin, A4[1] - margin + 8, A4[0]-margin, A4[1] - margin + 8)
        canvas.restoreState()

    doc_template = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin+12, bottomMargin=margin+8, title=title_text, author=institute or "Chemistry Notes Studio")
    story = []
    # Title block
    story.append(Paragraph(safe(title_text), title_style))
    subtitle = settings.get('subtitle', 'Study notes · Chemistry')
    if subtitle:
        story.append(Paragraph(safe(subtitle), sub_title_style))
    
    # Keep headings for bookmark tree
    headings_list = [b for b in doc.blocks if b.type in ('heading','subheading')]
    question_no = 0
    answers = []
    
    # Helper to parse table rows
    def _make_table(rows, header=True):
        if not rows:
            return Spacer(1,2)
        max_cols = max(len(r) for r in rows) if rows else 1
        # Normalize rows to same cols
        norm = []
        for r in rows:
            nr = list(r) + ['']*(max_cols-len(r))
            norm.append(nr)
        data = []
        for idx, r in enumerate(norm):
            row = [Paragraph(_rl_text(c), ParagraphStyle(f'TCell{idx}', parent=normal_style, fontName=font_bold if header and idx==0 else font_regular, fontSize=9.5, leading=12, alignment=TA_LEFT)) for c in r]
            data.append(row)
        col_width = (A4[0] - 2*margin - 10) / max_cols
        col_widths = [col_width]*max_cols
        tbl = Table(data, colWidths=col_widths, repeatRows=1 if header and len(data)>1 else 0)
        style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e7f1f2')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#204c55')),
            ('FONTNAME', (0,0), (-1,0), font_bold),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d4e0e5')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fcfb')]),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('RIGHTPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ])
        tbl.setStyle(style)
        return tbl

    for b in doc.blocks:
        typ = b.type
        data = b.meta or {}
        if typ == 'pagebreak':
            story.append(PageBreak())
            continue
        if typ == 'toc':
            story.append(Paragraph('Contents', h2_style))
            # Build TOC list
            for h in headings_list:
                # indentation for subheading
                indent = 12 if h.type == 'subheading' else 0
                toc_style = ParagraphStyle(f'TOC_{h.id}', parent=normal_style, leftIndent=indent, fontSize=10, leading=14, textColor=colors.HexColor('#244e70'))
                story.append(Paragraph(_rl_text(h.text), toc_style))
            story.append(Spacer(1, 8))
            continue
        if typ == 'heading':
            # Decorative star
            txt = f"★ {_rl_text(b.text)}" 
            p = Paragraph(txt, h1_style)
            story.append(p)
            # bookmark
            # ReportLab bookmarks via canvas.bookmarkPage - handled later but we track
            continue
        if typ == 'subheading':
            num = data.get('number','')
            txt = f"► {safe(num)} {_rl_text(b.text)}".strip()
            story.append(Paragraph(txt, h2_style))
            continue
        if typ == 'bullet':
            lev = getattr(b, 'level', 1)
            mark = "•" if lev>1 else "◆"
            body = _rl_text(b.text)
            style = bullet2_style if lev>1 else bullet_style
            # Use bulletText
            story.append(Paragraph(f'<font color="#1a8b7a">{mark}</font> &nbsp;{body}', style))
            continue
        if typ in ('box','example'):
            is_example = typ == 'example'
            label = data.get('title') or ('Solved Example' if is_example else 'Key Point')
            # Colors
            bg = colors.HexColor('#fff7e7') if is_example else colors.HexColor('#edf7f5')
            border_color = colors.HexColor('#e9a537') if is_example else colors.HexColor('#28a58e')
            title_style_local = example_title_style if is_example else box_title_style
            # For very long content, split into chunks to avoid LayoutError
            if len(b.text) > 2500:
                # Render as sequential flowables that can split across pages
                title_para = Paragraph(safe(label).upper(), title_style_local)
                story.append(Paragraph(f'<font color="{border_color.hexval() if hasattr(border_color, "hexval") else "#28a58e"}">▌</font> {title_para.text}', title_style_local))
                # Split body by sentences/segments to allow page breaks
                body_text = b.text
                # Chunk by ~1500 chars to allow splitting
                chunks = []
                while body_text:
                    if len(body_text) <= 1500:
                        chunks.append(body_text)
                        break
                    cut = body_text.rfind(' ', 0, 1500)
                    if cut < 500:
                        cut = 1500
                    chunks.append(body_text[:cut])
                    body_text = body_text[cut:]
                for ch in chunks:
                    story.append(Paragraph(_rl_text(ch), box_body_style))
                    story.append(Spacer(1, 2))
                # add visual separator
                story.append(HRFlowable(width="100%", thickness=0.5, color=border_color, spaceAfter=4, spaceBefore=2))
                continue
            title_para = Paragraph(safe(label).upper(), title_style_local)
            body_para = Paragraph(_rl_text(b.text), box_body_style)
            # Inner table with left border
            inner_data = [[title_para],[body_para]]
            inner_tbl = Table(inner_data, colWidths=[A4[0]-2*margin-12])
            inner_tbl.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), bg),
                ('BOX', (0,0), (-1,-1), 0.5, border_color),
                ('LINEBELOW', (0,0), (-1,0), 0.5, border_color),
                ('LEFTPADDING', (0,0), (-1,-1), 9),
                ('RIGHTPADDING', (0,0), (-1,-1), 9),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LINEBELOW', (0,0), (-1,0), 0, colors.white),
                ('LEFTPADDING', (0,0), (-1,0), 9),
            ]))
            # Wrap in table with left border
            outer = Table([[inner_tbl]], colWidths=[A4[0]-2*margin-4])
            outer.setStyle(TableStyle([
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 2),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ]))
            if len(b.text) > 3000:
                story.append(outer)
                story.append(Spacer(1, 4))
            else:
                # Use KeepTogether only for small boxes; allow split otherwise
                try:
                    story.append(KeepTogether([outer, Spacer(1,4)]))
                except Exception:
                    story.append(outer)
                    story.append(Spacer(1,4))
            continue
        if typ == 'table':
            rows = b.rows or []
            header = data.get('header', True) if isinstance(data, dict) else True
            # For compatibility, if header not in meta, assume True if first row looks header
            tbl = _make_table(rows, header=header)
            story.append(tbl)
            story.append(Spacer(1, 6))
            continue
        if typ == 'question':
            question_no += 1
            num = question_no
            marks = f' <font color="#64768a">[{safe(data.get("marks"))} marks]</font>' if data.get('marks') else ''
            q_body = _rl_text(b.text)
            story.append(Paragraph(f'<b>Q{num}.</b> {q_body}{marks}', question_style))
            opts = data.get('options',[]) or getattr(b,'items',[]) or []
            if opts:
                # Layout options: grid 2x2 vs single vertical
                layout = settings.get('optionLayout','grid')
                if layout == 'single':
                    for i,o in enumerate(opts):
                        key = o.get('key', chr(65+i)) if isinstance(o, dict) else chr(65+i)
                        txt_o = o.get('text','') if isinstance(o, dict) else str(o)
                        story.append(Paragraph(f'({safe(key)}) {_rl_text(txt_o)}', option_style))
                else:
                    # grid: 2 per row via Table
                    opt_paras = []
                    for i,o in enumerate(opts):
                        key = o.get('key', chr(65+i)) if isinstance(o, dict) else chr(65+i)
                        txt_o = o.get('text','') if isinstance(o, dict) else str(o)
                        opt_paras.append(Paragraph(f'({safe(key)}) {_rl_text(txt_o)}', option_style))
                    # Build rows of 2
                    rows = []
                    for i in range(0, len(opt_paras), 2):
                        row = opt_paras[i:i+2]
                        if len(row)==1:
                            row.append(Paragraph('', option_style))
                        rows.append(row)
                    if rows:
                        w = (A4[0]-2*margin-16)/2
                        t = Table(rows, colWidths=[w,w])
                        t.setStyle(TableStyle([
                            ('VALIGN', (0,0), (-1,-1), 'TOP'),
                            ('LEFTPADDING', (0,0), (-1,-1), 2),
                            ('RIGHTPADDING', (0,0), (-1,-1), 2),
                            ('TOPPADDING', (0,0), (-1,-1), 2),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                        ]))
                        story.append(t)
            answer = data.get('answer')
            if answer:
                answers.append((num, answer))
                if settings.get('answerMode') == 'inline':
                    story.append(Paragraph(f'<font color="#19806d">Answer: {_rl_text(answer)}</font>', answer_style))
            # Add separator for question theme
            if theme == 'question':
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dfe7e5'), spaceAfter=6, spaceBefore=2))
            elif theme == 'worksheet':
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#ccd8d3'), spaceAfter=8, spaceBefore=2, lineCap='round', dash=(3,3)))
            else:
                story.append(Spacer(1,4))
            continue
        if typ == 'equation':
            from .mathmini import render_math
            # Try to render via mathmini then strip
            try:
                math_html = render_math(b.text, chem_inline=lambda t: _rl_text(t), display=True)
                math_text = _strip_math_html(math_html)
            except Exception:
                math_text = b.text
            # Centered
            eq_style = ParagraphStyle('Equation', parent=normal_style, alignment=TA_CENTER, fontSize=11, leading=16, spaceBefore=5, spaceAfter=6, textColor=colors.HexColor('#15365c'))
            story.append(Paragraph(safe(math_text), eq_style))
            continue
        if typ == 'image':
            src = b.src or ''
            caption = b.text or ''
            if src.startswith('data:image/'):
                try:
                    # data:image/png;base64,....
                    header, b64data = src.split(',',1)
                    img_bytes = base64.b64decode(b64data)
                    img_buf = io.BytesIO(img_bytes)
                    # Determine format
                    from PIL import Image as PILImage
                    pil = PILImage.open(img_buf)
                    w, h = pil.size
                    # Scale to max width 70%
                    max_w = (A4[0]-2*margin) * 0.70
                    max_h = 19*cm
                    # Convert px to points roughly: assume 96 dpi, 1pt=1/72 inch
                    # We will scale image to fit
                    scale = min(max_w / (w * 72/96) if w else 1, max_h / (h * 72/96) if h else 1, 1)
                    # Use reportlab Image with width/height
                    img_buf.seek(0)
                    img = Image(img_buf, width=w*scale*0.75, height=h*scale*0.75)  # approximate
                    img.hAlign = 'CENTER'
                    story.append(img)
                    if caption:
                        story.append(Paragraph(_rl_text(caption), small_style))
                except Exception as e:
                    story.append(Paragraph(f'<font color="#b45039">Diagram: {safe(str(e))} { _rl_text(caption) }</font>', small_style))
            else:
                story.append(Paragraph(f'<font color="#b45039">Diagram: use a data:image URL in JSON. {_rl_text(caption)}</font>', small_style))
            story.append(Spacer(1,4))
            continue
        # default para
        story.append(Paragraph(_rl_text(b.text), normal_style))
    
    # Answer key on separate page if needed
    if answers and settings.get('answerMode') == 'separate':
        story.append(PageBreak())
        story.append(Paragraph('Answer Key', h1_style))
        for n, a in answers:
            story.append(Paragraph(f'<b>Q{n}.</b> {_rl_text(a)}', normal_style))
    
    # Build
    doc_template.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_bytes = buffer.getvalue()
    # Count pages via pypdfium2 for accuracy
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_bytes)
        num_pages = len(pdf)
        pdf.close()
    except Exception:
        # fallback estimate: use platypus page count if available, else 1
        num_pages = getattr(doc_template, 'page', 1)
        if num_pages == 0:
            num_pages = 1
    # Headings for bookmark tree
    bm = []
    for h in headings_list:
        bm.append({"label": h.text, "id": h.id, "type": h.type})
    return _FallbackResult(pdf_bytes, num_pages, bm)

def render(source, settings):
    markup, doc = make_html(source, settings)
    # Try WeasyPrint first if available and functional
    if _can_use_weasy():
        try:
            from weasyprint import HTML as WPHTML
            from weasyprint.urls import URLFetcher
            result = WPHTML(string=markup, base_url=ROOT.as_uri(), url_fetcher=URLFetcher(allowed_protocols=("file", "data"))).render()
            return result, markup, doc
        except Exception as e:
            # fallback on failure
            pass
    # Fallback to ReportLab
    fb = _build_fallback_pdf(doc, settings, markup)
    return fb, markup, doc
