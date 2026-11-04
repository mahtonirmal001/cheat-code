from flask import Flask, request, jsonify, render_template, send_file, make_response
from engine.render import render, get_doc
from engine.chem import scan_glyphs, repair
import io, base64, logging, re, json
from pathlib import Path
import pypdfium2 as pdfium
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.logger.setLevel(logging.INFO)
sample = Path('samples/demo.md').read_text(encoding='utf-8')

# CORS for Arena preview
@app.after_request
def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    # Allow iframe embedding for preview
    resp.headers.pop('X-Frame-Options', None)
    return resp

def payload():
    d = request.get_json(force=True)
    source = str(d.get('source', ''))
    if len(source) > 200000:
        raise ValueError('Content is too long (maximum 200,000 characters).')
    return source, d.get('settings') or {}

@app.get('/')
def index():
    return render_template('index.html', sample=sample)

@app.get('/api/health')
def health():
    return jsonify(status='ok', version='2.0-fallback', weasy='fallback-reportlab')

@app.get('/api/sample')
def get_sample():
    return jsonify(source=sample)

@app.post('/api/preview')
def preview():
    try:
        source, settings = payload()
        # Optional glyph scan warning
        glyphs = scan_glyphs(source) if len(source) < 50000 else []
        result, _, doc = render(source, settings)
        data = result.write_pdf()
        pdf = pdfium.PdfDocument(data)
        pages = []
        dpi_scale = 1.6  # higher quality
        for i in range(min(len(pdf), 20)):
            page = pdf[i]
            try:
                bitmap = page.render(scale=dpi_scale)
                out = io.BytesIO()
                pil = bitmap.to_pil()
                # Optional: add slight padding/shadow effect via white background already
                pil.save(out, format='PNG', optimize=True)
                pages.append(base64.b64encode(out.getvalue()).decode())
            finally:
                try:
                    page.close()
                except:
                    pass
        count = len(pdf) if hasattr(pdf, '__len__') else len(result.pages)
        pdf.close()
        # doc.blocks count, glyph warnings
        return jsonify(
            pages=pages,
            count=count,
            blocks=len(doc.blocks),
            truncated=count > 20,
            glyphs=glyphs[:5],
            pages_total=count
        )
    except Exception as e:
        app.logger.exception('Preview failed')
        return jsonify(error=str(e)), 400

@app.post('/api/export/<kind>')
def export(kind):
    try:
        source, settings = payload()
        result, markup, doc = render(source, settings)
        safe_title = re.sub(r'[^A-Za-z0-9_\- ]+', '', settings.get('title') or 'chemistry-notes').strip().replace(' ', '-') or 'chemistry-notes'
        if kind == 'pdf':
            pdf_bytes = result.write_pdf()
            return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name=f'{safe_title}.pdf')
        if kind == 'html':
            # Embed fonts for portable HTML export
            for f in (Path(__file__).parent / 'fonts').glob('*.ttf'):
                uri = f.resolve().as_uri()
                if uri in markup:
                    markup = markup.replace(uri, 'data:font/ttf;base64,' + base64.b64encode(f.read_bytes()).decode())
            # Add meta title
            return send_file(io.BytesIO(markup.encode('utf-8')), mimetype='text/html', as_attachment=True, download_name=f'{safe_title}.html')
        if kind == 'docx':
            d = Document()
            # Set narrow margins for more content
            for section in d.sections:
                section.top_margin = Inches(0.7)
                section.bottom_margin = Inches(0.7)
                section.left_margin = Inches(0.8)
                section.right_margin = Inches(0.8)
                # Header: institute
                if settings.get('institute'):
                    header = section.header.paragraphs[0]
                    header.text = settings.get('institute','')
                    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    for run in header.runs:
                        run.font.size = Pt(8)
                        run.font.color.rgb = RGBColor(0x71, 0x80, 0x96)
                footer = section.footer.paragraphs[0]
                footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
                footer.text = "Chemistry Notes Studio"
                for run in footer.runs:
                    run.font.size = Pt(8)
                    run.font.color.rgb = RGBColor(0x71, 0x80, 0x96)
            # Styles
            style = d.styles['Normal']
            style.font.name = 'Calibri'
            style.font.size = Pt(10.5)
            style.paragraph_format.space_after = Pt(6)
            # Title
            title = d.add_heading(settings.get('title') or 'Chemistry Notes', 0)
            title.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in title.runs:
                run.font.color.rgb = RGBColor(0x15, 0x36, 0x5c)
            if settings.get('subtitle'):
                p = d.add_paragraph(settings.get('subtitle'))
                p.runs[0].font.color.rgb = RGBColor(0x69, 0x80, 0x92)
                p.runs[0].font.size = Pt(9)
            # Watermark simulation via heading if set
            if settings.get('watermark'):
                p = d.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(f"— {settings.get('watermark')} —")
                run.font.color.rgb = RGBColor(0x94, 0xa4, 0x9e)
                run.font.italic = True
                run.font.size = Pt(9)
            for b in doc.blocks:
                if b.type == 'heading':
                    h = d.add_heading(b.text, 1)
                    for run in h.runs:
                        run.font.color.rgb = RGBColor(0x17, 0x3b, 0x68)
                elif b.type == 'subheading':
                    meta = b.meta or {}
                    num = meta.get('number','')
                    h = d.add_heading(f"{num} {b.text}".strip(), 2)
                    for run in h.runs:
                        run.font.color.rgb = RGBColor(0x19, 0x80, 0x6d)
                elif b.type == 'table' and b.rows:
                    rows = b.rows
                    cols = max(len(r) for r in rows) if rows else 1
                    t = d.add_table(rows=0, cols=cols)
                    t.style = 'Light Grid Accent 1'
                    # t.style = 'Table Grid'
                    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for idx, row in enumerate(rows):
                        cells = t.add_row().cells
                        for i, c in enumerate(row):
                            # pad to cols
                            if i < len(cells):
                                cells[i].text = str(c)
                                # header styling
                                if idx == 0 and (b.meta or {}).get('header', True):
                                    for p in cells[i].paragraphs:
                                        for run in p.runs:
                                            run.bold = True
                                            run.font.color.rgb = RGBColor(0x20, 0x4c, 0x55)
                                    shading = cells[i]._element.get_or_add_tcPr()
                                    # background not easily set via python-docx without extension, keep simple
                                cells[i].paragraphs[0].runs[0].font.size = Pt(9) if cells[i].paragraphs[0].runs else Pt(9)
                    d.add_paragraph('', style='Normal')  # spacer
                elif b.type == 'pagebreak':
                    d.add_page_break()
                elif b.type == 'toc':
                    p = d.add_paragraph()
                    run = p.add_run('Contents')
                    run.bold = True
                    run.font.size = Pt(12)
                    for h in [x for x in doc.blocks if x.type == 'heading']:
                        p = d.add_paragraph(h.text, style='List Bullet')
                        p.paragraph_format.left_indent = Inches(0.2)
                    continue
                elif b.type == 'question':
                    meta = b.meta or {}
                    # Find question number via order
                    # We need to track globally but doc.blocks order matches
                    # Use meta num or incremental
                    qnum = meta.get('num') or str(len([x for x in doc.blocks[:doc.blocks.index(b)+1] if x.type=='question']))
                    marks = f"  [{meta.get('marks')} marks]" if meta.get('marks') else ""
                    p = d.add_paragraph()
                    run = p.add_run(f"Q{qnum}. {b.text}{marks}")
                    run.bold = True
                    for o in meta.get('options', []):
                        p2 = d.add_paragraph(f"({o.get('key','')}) {o.get('text','')}", style='List Bullet 2' if len(meta.get('options',[]))>2 else 'Normal')
                        p2.paragraph_format.left_indent = Inches(0.3)
                    if meta.get('answer') and settings.get('answerMode') == 'inline':
                        p3 = d.add_paragraph()
                        run = p3.add_run(f"Answer: {meta.get('answer')}")
                        run.font.color.rgb = RGBColor(0x19, 0x80, 0x6d)
                        run.italic = True
                elif b.type in ('box','example'):
                    meta = b.meta or {}
                    title = meta.get('title', 'Note')
                    p = d.add_paragraph()
                    run = p.add_run(title)
                    run.bold = True
                    run.font.color.rgb = RGBColor(0xa5, 0x68, 0x15) if b.type=='example' else RGBColor(0x18, 0x79, 0x63)
                    run.font.size = Pt(9)
                    p2 = d.add_paragraph(b.text)
                    p2.paragraph_format.left_indent = Inches(0.15)
                    # Add left border simulation via paragraph shading? Keep simple
                    if b.type == 'example':
                        p2.paragraph_format.space_after = Pt(8)
                    # keep together
                    p.paragraph_format.keep_together = True
                    p2.paragraph_format.keep_together = True
                elif b.type == 'equation':
                    p = d.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run(b.text)
                    run.italic = True
                    run.font.size = Pt(11)
                elif b.type == 'image':
                    if b.src and b.src.startswith('data:image/'):
                        try:
                            header, b64d = b.src.split(',',1)
                            img_data = base64.b64decode(b64d)
                            img_bio = io.BytesIO(img_data)
                            # Use section width
                            d.add_picture(img_bio, width=Inches(4.5))
                            if b.text:
                                cap = d.add_paragraph(b.text)
                                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                                for run in cap.runs:
                                    run.font.size = Pt(9)
                                    run.font.color.rgb = RGBColor(0x70, 0x80, 0x90)
                        except Exception as e:
                            d.add_paragraph(f"[Image error: {e}]")
                    else:
                        p = d.add_paragraph(f"[Diagram: {b.text}]")
                        p.runs[0].font.color.rgb = RGBColor(0xb4, 0x50, 0x39)
                else:
                    # bullet or para
                    prefix = '◆ ' if b.type == 'bullet' else ''
                    if b.level == 2:
                        prefix = '   • '
                    p = d.add_paragraph(f"{prefix}{b.text}")
                    if b.level == 2:
                        p.paragraph_format.left_indent = Inches(0.3)
                    # keep widow/orphan
                    p.paragraph_format.widow_control = True
            # Answer key separate page
            answers = [(b.meta.get('num'), b.meta.get('answer')) for b in doc.blocks if b.type=='question' and (b.meta or {}).get('answer')]
            if answers and settings.get('answerMode') == 'separate':
                d.add_page_break()
                h = d.add_heading('Answer Key', 1)
                for n, a in answers:
                    p = d.add_paragraph()
                    run = p.add_run(f"Q{n}. ")
                    run.bold = True
                    p.add_run(str(a))
            out = io.BytesIO()
            d.save(out)
            out.seek(0)
            return send_file(out, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', as_attachment=True, download_name=f'{safe_title}.docx')
        return jsonify(error='Unknown format'), 404
    except Exception as e:
        app.logger.exception('Export failed')
        return jsonify(error=str(e)), 400

@app.post('/api/scan')
def scan():
    try:
        d = request.get_json(force=True)
        source = str(d.get('source',''))
        glyphs = scan_glyphs(source)
        return jsonify(glyphs=glyphs, repaired=repair(source)[:2000])
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.post('/api/repair')
def repair_api():
    try:
        d = request.get_json(force=True)
        source = str(d.get('source',''))
        return jsonify(repaired=repair(source))
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.post('/api/import-pdf')
def import_pdf():
    """Extract text from uploaded PDF to help user import existing PDFs"""
    try:
        if 'file' not in request.files:
            return jsonify(error='No file uploaded'), 400
        f = request.files['file']
        data = f.read()
        if len(data) > 8*1024*1024:
            return jsonify(error='PDF too large (max 8 MB)'), 400
        doc = pdfium.PdfDocument(data)
        texts = []
        for i in range(min(len(doc), 30)):
            page = doc[i]
            tp = page.get_textpage()
            txt = tp.get_text_range()
            texts.append(txt)
            tp.close()
            page.close()
        doc.close()
        full = "\n\n".join(texts)
        # Basic cleanup: try to detect headings
        # Suggest conversion hints
        return jsonify(text=full[:200000], pages=len(texts), truncated=len(texts)==30)
    except Exception as e:
        app.logger.exception('PDF import failed')
        return jsonify(error=str(e)), 400

@app.post('/api/validate')
def validate():
    try:
        source, settings = payload()
        doc = get_doc(source)
        issues = []
        if len(source.strip()) < 20:
            issues.append({"level":"info", "msg":"Content is very short — add more details for a complete document."})
        headings = [b for b in doc.blocks if b.type=='heading']
        if not headings:
            issues.append({"level":"warn", "msg":"No topic headings (★) found — add at least one ★ heading for structure."})
        tables = [b for b in doc.blocks if b.type=='table']
        for t in tables:
            if t.rows and any(len(r) != len(t.rows[0]) for r in t.rows):
                issues.append({"level":"warn", "msg":f"Table with inconsistent columns detected near: {t.rows[0][0][:40]}..."})
        glyphs = scan_glyphs(source)
        if glyphs:
            issues.append({"level":"warn", "msg":f"Found {len(glyphs)} suspicious glyph(s) (e.g., {glyphs[0]['char']} U+{ord(glyphs[0]['char']):04X}) — they will be auto-repaired but please proofread formulas."})
        # Check images
        images = [b for b in doc.blocks if b.type=='image']
        for im in images:
            if not im.src.startswith('data:image/'):
                issues.append({"level":"warn", "msg":"Image without data:image URL will appear as placeholder — embed as data URL in JSON."})
        return jsonify(issues=issues, blocks=len(doc.blocks), headings=len(headings))
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.errorhandler(413)
def too_large(e):
    return jsonify(error='File is too large (limit 10 MB)'), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify(error='Not found'), 404

if __name__ == '__main__':
    # threaded is better for preview concurrency
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
