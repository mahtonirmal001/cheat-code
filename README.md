# Chemistry Notes Studio

A local Flask app for writing structured chemistry notes and exporting PDF, HTML and basic DOCX.

## Start

Python 3.10+ and the native dependencies required by WeasyPrint are needed. Install with `pip install -r requirements.txt`, then run `python app.py`. Open http://localhost:8000. Bundled Noto fonts are from Google Fonts (SIL Open Font License).

## Input

The editor accepts the included sample format or JSON with a `blocks` array. Use `★`, `►`, `◆`, and `•` at the beginning of lines. Markdown **bold**, pipe tables, `::: example` … `:::`, `::: keypoint` … `:::`, `[toc]`, `[pagebreak]`, and `[eq] LaTeX subset [/eq]` are supported. Questions start with `Q1.` followed by options `(A)` on separate lines and optional `[ans]`. Numbers are assigned automatically. JSON examples: `{"blocks":[{"type":"heading","text":"Chapter"},{"type":"question","text":"What?","meta":{"marks":2,"options":[{"key":"A","text":"H2O"}],"answer":"A"}}]}`. For a diagram use a JSON image block with an embedded `data:image/...` URL. External URLs and local paths are not supported.

## Important limitations

Pagination uses WeasyPrint CSS break avoidance, repeated table headers, and paragraph widow/orphan rules. A block taller than a page may split; oversized rows and two-column layout can still behave differently. Preview and test your document before printing. This is not a full TeX/mhchem implementation: ambiguous chemical charges and corrupted extracted characters may need manual correction; proofread all formulas and don't use the automatic repair on Odia-language text. DOCX is a basic editable text export and does not faithfully reproduce PDF math, chemistry formatting or pagination. HTML uses embedded fonts, but paged features depend on the browser. Template options change styling, not content. No automatic smart reordering, auto-fit, batch processing, SMILES drawing, watermark, logo, direct PDF import, or full WYSIWYG editing yet. Preview shows at most 20 pages; PDF export includes all pages. Save/load stores the source and settings in a JSON file on your device.
