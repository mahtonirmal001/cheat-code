import html, re, json
from pathlib import Path
from .chem import inline
from .parser import parse, parse_json
from weasyprint import HTML
from weasyprint.urls import URLFetcher
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
    @page {{size:A4; margin:2cm; @top-left {{ content: "{safe(title).replace(chr(34),'')}"; font: 8pt Noto,Devanagari,sans-serif; color:#718096; }} @top-right {{content:"{safe(settings.get('institute','')).replace(chr(34),'')}"; font:8pt Noto,Devanagari,sans-serif; color:#718096;}} @bottom-center {{content: "Page " counter(page) " of " counter(pages); font:8pt Noto,sans-serif;color:#718096;}} }}
    * {{box-sizing:border-box}} body {{font-family:Noto,Devanagari,sans-serif;font-size:{size}pt;line-height:1.4;color:#24344a;font-variant-ligatures:none; overflow-wrap:anywhere;}} h1,h2,p {{margin:0}} .doc-title {{font-size:20pt;color:#15365c;margin:0 0 4pt;font-weight:700}} .doc-sub {{color:#698092;margin-bottom:16pt;font-size:9pt}} .block {{margin:0 0 {5 if compact else 8}pt}} .keep {{break-inside:avoid;}} .with-next {{break-after:avoid}} .force,.pagebreak {{break-before:page}} .pagebreak {{height:0}} h1 {{font-size:16pt;color:#173b68; margin:13pt 0 5pt;bookmark-level:1;break-after:avoid}} h2 {{font-size:12pt;color:#19806d; margin:9pt 0 4pt;bookmark-level:none;break-after:avoid}} p, .bullet {{orphans:3;widows:3}} .bullet {{display:flex;gap:7pt}} .mark {{color:#1a8b7a}} .level2 {{margin-left:17pt}} strong,b {{font-weight:700}} sup,sub {{font-size:70%;line-height:0}} .box-inner {{background:#edf7f5;border-left:3pt solid #28a58e;padding:9pt 11pt;border-radius:3pt;white-space:normal}} .example .box-inner {{background:#fff7e7;border-color:#e9a537}} .box-title {{font-size:9pt;color:#187963;font-weight:700;margin-bottom:4pt;text-transform:uppercase;letter-spacing:.04em}} .example .box-title {{color:#a56815}} table {{border-collapse:collapse;width:100%;font-size:9.5pt}} thead {{display:table-header-group}} tr {{break-inside:avoid}} th,td {{border:0.5pt solid #d4e0e5;padding:5pt 6pt;text-align:left;vertical-align:top}} th {{background:#e7f1f2;color:#204c55}} .qtitle {{position:relative;padding-right:40pt}} .marks {{float:right;font-size:8pt;color:#64768a}} .options {{display:block;margin:6pt 0 0 16pt}} .options > div {{display:inline-block;width:49%;vertical-align:top;padding:2pt}} .options.single > div {{display:block;width:100%}} .answer {{color:#19806d;margin-top:5pt}} figure {{margin:0;text-align:center}} img {{max-width:100%;max-height:19cm}} figcaption {{font-size:9pt;color:#708090}} .missing {{color:#b45039}} .toc-list {{padding-left:20pt}} .toc-list a {{color:#244e70;text-decoration:none}} .toc-list a::after {{content:leader('.') target-counter(attr(href), page)}} .content {{ {'column-count:2;column-gap:18pt;' if columns else ''} }}
    '''
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body><div class="doc-title">{safe(title)}</div><div class="doc-sub">{safe(settings.get("subtitle", "Study notes · Chemistry"))}</div><main class="content">{"".join(parts)}</main></body></html>',doc

def render(source, settings):
    markup, doc = make_html(source,settings)
    result=HTML(string=markup,base_url=ROOT.as_uri(),url_fetcher=URLFetcher(allowed_protocols=("file", "data"))).render()
    return result,markup,doc
