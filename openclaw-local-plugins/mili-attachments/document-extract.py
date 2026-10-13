"""Bounded Office/OpenDocument extraction. Never executes document code or links."""
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

LIMIT = 40_000
MAX_EXPANDED = 40 * 1024 * 1024


def local(tag):
    return tag.rsplit('}', 1)[-1]


def extract(file, start=0):
    suffix = file.suffix.lower()
    chunks = []
    with zipfile.ZipFile(file) as archive:
        infos = archive.infolist()
        if len(infos) > 10_000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError('Document expands beyond 40 MiB / 10000 entries')
        names = set(archive.namelist())

        def xml(name):
            data = archive.read(name)
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ValueError('XML document entities are forbidden')
            return ET.fromstring(data)

        if suffix in ('.docx', '.docm'):
            for name in ['word/document.xml', 'word/footnotes.xml', 'word/endnotes.xml'] + sorted(n for n in names if n.startswith(('word/header', 'word/footer')) and n.endswith('.xml')):
                if name not in names:
                    continue
                root = xml(name)
                def paragraph(node):
                    return ''.join((n.text or '') if local(n.tag) == 't' else '\t' if local(n.tag) == 'tab' else '\n' if local(n.tag) == 'br' else '' for n in node.iter())

                def walk(node):
                    if local(node.tag) == 'tbl':
                        for row in node:
                            if local(row.tag) == 'tr':
                                chunks.append('\t'.join(' / '.join(paragraph(p) for p in cell.iter() if local(p.tag) == 'p') for cell in row if local(cell.tag) == 'tc'))
                    elif local(node.tag) == 'p':
                        chunks.append(paragraph(node))
                    else:
                        for child in node:
                            walk(child)

                walk(root)
        elif suffix in ('.xlsx', '.xlsm'):
            shared = []
            if 'xl/sharedStrings.xml' in names:
                shared = [''.join(n.text or '' for n in item.iter() if local(n.tag) == 't') for item in xml('xl/sharedStrings.xml')]
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            rels = {r.attrib['Id']: r.attrib['Target'] for r in xml('xl/_rels/workbook.xml.rels')}
            for sheet in xml('xl/workbook.xml').findall('s:sheets/s:sheet', ns):
                target = rels[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                name = target.lstrip('/') if target.startswith('/') else 'xl/' + target
                chunks.append('--- sheet: ' + sheet.attrib['name'] + ' (raw stored values; formulas not recalculated) ---')
                for row in xml(name).iter():
                    if local(row.tag) != 'row':
                        continue
                    fields = []
                    for cell in row:
                        value = cell.find('s:v', ns)
                        text = value.text if value is not None else ''.join(n.text or '' for n in cell.iter() if local(n.tag) == 't')
                        if cell.attrib.get('t') == 's' and text:
                            text = shared[int(text)]
                        formula = cell.find('s:f', ns)
                        if formula is not None:
                            text = '[formula, cached value=' + str(text) + ']'
                        fields.append(cell.attrib.get('r', '?') + '=' + str(text or ''))
                    chunks.append('\t'.join(fields))
        elif suffix in ('.pptx', '.pptm'):
            slides = sorted((n for n in names if n.startswith('ppt/slides/slide') and n.endswith('.xml')), key=lambda n: int(Path(n).stem[5:]))
            for name in slides:
                chunks.append('--- ' + Path(name).stem + ' ---')
                chunks.extend(n.text or '' for n in xml(name).iter() if local(n.tag) == 't')
        elif suffix in ('.odt', '.ods', '.odp'):
            root = xml('content.xml')
            chunks.extend(''.join(n.itertext()) for n in root.iter() if local(n.tag) in ('p', 'h'))
        else:
            raise ValueError('Unsupported structured document')
    text = '\n'.join(chunks)
    if start < 0 or start > len(text):
        raise ValueError('Text offset outside document')
    end = min(start + LIMIT, len(text))
    return {'text': text[start:end], 'truncated': end < len(text), 'nextChar': end if end < len(text) else None, 'totalChars': len(text), 'mode': 'document-text'}


if __name__ == '__main__':
    try:
        print(json.dumps(extract(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 0), ensure_ascii=False))
    except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError) as error:
        sys.exit('Document extraction failed: ' + str(error))
