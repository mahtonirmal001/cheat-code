from flask import Flask, request, jsonify, render_template, send_file
from engine.render import render
import io, base64, logging
from pathlib import Path
import pypdfium2 as pdfium
from docx import Document
app=Flask(__name__); app.config['MAX_CONTENT_LENGTH']=4*1024*1024
sample=Path('samples/demo.md').read_text()

def payload():
    d=request.get_json(force=True); source=str(d.get('source',''))
    if len(source)>150000: raise ValueError('Content is too long (maximum 150,000 characters).')
    return source,d.get('settings') or {}
@app.get('/')
def index(): return render_template('index.html',sample=sample)
@app.post('/api/preview')
def preview():
    try:
        source,settings=payload(); result,_,doc=render(source,settings); data=result.write_pdf(); pdf=pdfium.PdfDocument(data)
        pages=[]
        for i in range(min(len(pdf),20)):
            page=pdf[i]; bitmap=page.render(scale=1.05); out=io.BytesIO(); bitmap.to_pil().save(out,format='PNG',optimize=True); pages.append(base64.b64encode(out.getvalue()).decode()); page.close()
        pdf.close()
        return jsonify(pages=pages,count=len(result.pages),blocks=len(doc.blocks),truncated=len(result.pages)>20)
    except Exception as e:
        app.logger.exception('Preview failed'); return jsonify(error=str(e)),400
@app.post('/api/export/<kind>')
def export(kind):
    try:
        source,settings=payload(); result,markup,doc=render(source,settings)
        if kind=='pdf': return send_file(io.BytesIO(result.write_pdf()),mimetype='application/pdf',as_attachment=True,download_name='chemistry-notes.pdf')
        if kind=='html':
            # Embed fonts for a portable HTML export.
            import re
            for f in (Path(__file__).parent/'fonts').glob('*.ttf'):
                uri=f.resolve().as_uri()
                if uri in markup: markup=markup.replace(uri,'data:font/ttf;base64,'+base64.b64encode(f.read_bytes()).decode())
            return send_file(io.BytesIO(markup.encode()),mimetype='text/html',as_attachment=True,download_name='chemistry-notes.html')
        if kind=='docx':
            d=Document(); d.add_heading(settings.get('title','Chemistry Notes'),0)
            for b in doc.blocks:
                if b.type=='heading': d.add_heading(b.text,1)
                elif b.type=='subheading': d.add_heading(b.text,2)
                elif b.type=='table' and b.rows:
                    t=d.add_table(rows=0,cols=max(len(r) for r in b.rows)); t.style='Table Grid'
                    for row in b.rows:
                        cells=t.add_row().cells
                        for i,c in enumerate(row): cells[i].text=str(c)
                elif b.type=='pagebreak': d.add_page_break()
                elif b.type=='toc': continue
                else:
                    if b.type in ('box','example'): d.add_paragraph((b.meta or {}).get('title','Note')).runs[0].bold=True
                    p=d.add_paragraph(('◆ ' if b.type=='bullet' else '')+b.text)
                    p.paragraph_format.keep_together=b.type in ('box','example','question')
                    for o in (b.meta or {}).get('options',[]): d.add_paragraph('('+o.get('key','')+') '+o.get('text',''))
            out=io.BytesIO(); d.save(out); out.seek(0)
            return send_file(out,mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',as_attachment=True,download_name='chemistry-notes.docx')
        return jsonify(error='Unknown format'),404
    except Exception as e:
        app.logger.exception('Export failed'); return jsonify(error=str(e)),400
if __name__=='__main__': app.run(host='0.0.0.0',port=8000,debug=False,threaded=True)
