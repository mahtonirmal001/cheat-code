import unittest
from engine.render import render
import pypdfium2 as pdfium

class RenderTests(unittest.TestCase):
    def test_sample_text_and_bookmarks(self):
        src=open('samples/demo.md').read(); doc,_,_=render(src,{'title':'Chemistry'}); data=doc.write_pdf()
        pdf=pdfium.PdfDocument(data); text=''.join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
        self.assertIn('Coordination Compounds',text); self.assertIn('ligand',text.lower()); self.assertTrue(doc.make_bookmark_tree()); self.assertGreaterEqual(len(pdf),1)
    def test_force_break(self):
        doc,_,_=render('★ First\nSome content\n[pagebreak]\n★ Second\nMore text',{}); self.assertEqual(len(doc.pages),2)
    def test_oversize_example(self):
        doc,_,_=render('★ Long\n::: example\n'+('A very long sentence with H2O and chemistry. ' * 1000)+'\n:::',{}); self.assertGreater(len(doc.pages),1)
        self.assertLess(len(doc.pages),40)
    def test_table(self):
        src='★ Table\n| Name | Value |\n| --- | --- |\n'+''.join('| row %d | H2O |\n'%i for i in range(100))
        doc,_,_=render(src,{}); self.assertGreater(len(doc.pages),1)
        pdf=pdfium.PdfDocument(doc.write_pdf()); self.assertIn('Name',pdf[1].get_textpage().get_text_range())
if __name__ == '__main__': unittest.main()
