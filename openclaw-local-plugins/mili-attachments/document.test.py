import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('extractor', Path(__file__).with_name('document-extract.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Documents(unittest.TestCase):
    def document(self, suffix, files):
        directory = tempfile.TemporaryDirectory(prefix='mili-doc-test-')
        self.addCleanup(directory.cleanup)
        file = Path(directory.name) / ('test' + suffix)
        with zipfile.ZipFile(file, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return file

    def test_docx_continuation(self):
        file = self.document('.docx', {'word/document.xml': '<document><p><t>' + 'A' * 40020 + '</t></p><p><t>Bank Mandiri</t></p></document>'})
        first = module.extract(file)
        self.assertTrue(first['truncated'])
        second = module.extract(file, first['nextChar'])
        self.assertIn('Bank Mandiri', second['text'])
        self.assertIsNone(second['nextChar'])
        self.assertEqual(len(first['text'] + second['text']), first['totalChars'])

    def test_xlsx_preserves_sparse_cell_coordinates_and_sheet_name(self):
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        file = self.document('.xlsx', {
            'xl/workbook.xml': f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Banks" r:id="rId1"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            'xl/sharedStrings.xml': f'<sst xmlns="{ns}"><si><t>HSBC</t></si></sst>',
            'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{ns}"><sheetData><row r="2"><c r="A2" t="s"><v>0</v></c><c r="D2"><v>42</v></c><c r="E2"><f>D2*2</f><v>84</v></c></row></sheetData></worksheet>',
        })
        text = module.extract(file)['text']
        self.assertIn('sheet: Banks', text)
        self.assertIn('A2=HSBC\tD2=42\tE2=[formula, cached value=84]', text)

    def test_pptx_and_opendocument(self):
        file = self.document('.pptx', {'ppt/slides/slide2.xml': '<slide><t>Second</t></slide>', 'ppt/slides/slide1.xml': '<slide><t>First</t></slide>'})
        self.assertLess(module.extract(file)['text'].index('First'), module.extract(file)['text'].index('Second'))
        file = self.document('.odt', {'content.xml': '<document><p>Readable content</p></document>'})
        self.assertIn('Readable content', module.extract(file)['text'])

    def test_entities_and_corrupt_files_rejected(self):
        file = self.document('.docx', {'word/document.xml': '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///private">]><document><p>&secret;</p></document>'})
        with self.assertRaises(ValueError):
            module.extract(file)


if __name__ == '__main__':
    unittest.main()
