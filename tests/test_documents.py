"""Folder of bank documents to Markdown, on tiny fixtures written here. Run: .venv/bin/python -m unittest tests.test_documents"""
import datetime, os, pathlib, shutil, subprocess, sys, tempfile, unittest, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from builder import documents

DOCX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Gecikme Politikası</w:t></w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">Müşteri çğıöşü </w:t></w:r><w:r><w:t>harflerini görür.</w:t></w:r></w:p>
<w:p/><w:p/><w:p/>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>İlk madde</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Bant</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Gün</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>erken</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1-7</w:t></w:r></w:p><w:p><w:r><w:t>gün</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p><w:r><w:t>Son paragraf.</w:t></w:r></w:p><w:sectPr/></w:body></w:document>"""
SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
WORKBOOK = ('<workbook xmlns="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            '<sheet name="Tatiller" sheetId="1" r:id="rId1"/><sheet name="Bantlar" sheetId="2" r:id="rId2"/></sheets></workbook>' % SS)
RELS = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="x" Target="/xl/worksheets/sheet2.xml"/></Relationships>')
SHARED = '<sst xmlns="%s"><si><t>Tarih</t></si><si><t>Açıklama</t></si><si><r><t>Cumhuriyet </t></r><r><t>Bayramı</t></r></si></sst>' % SS
STYLES = ('<styleSheet xmlns="%s"><numFmts count="1"><numFmt numFmtId="164" formatCode="dd.mm.yyyy"/></numFmts>'
          '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>' % SS)
SERIAL = (datetime.date(2026, 10, 29) - datetime.date(1899, 12, 30)).days
SHEET1 = ('<worksheet xmlns="%s"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"/>'
          '<row r="3"><c r="A3" s="1"><v>%d</v></c><c r="B3" t="s"><v>2</v></c></row>'
          '<row r="4"><c r="A4"><v>42</v></c><c r="C4" t="inlineStr"><is><t>satır içi</t></is></c></row></sheetData></worksheet>' % (SS, SERIAL))
SHEET2 = '<worksheet xmlns="%s"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>erken</t></is></c><c r="B1"><v>7</v></c></row></sheetData></worksheet>' % SS


def write_zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "sub").mkdir()
        (self.dir / "README.md").write_text("# Belgeler\n", encoding="utf-8")
        (self.dir / "BRIEF.md").write_text("# Özet\nçğıöşü\n", encoding="utf-8")
        (self.dir / "sub" / "c.md").write_text("alt klasör\n", encoding="utf-8")
        (self.dir / "zzz.txt").write_text("﻿BOM'lu metin\n", encoding="utf-8")
        (self.dir / "flow.png").write_bytes(b"\x89PNG garbage")
        (self.dir / "x.bin").write_bytes(b"\x00\x01")
        (self.dir / "bad.pdf").write_bytes(b"%PDF-1.4 garbage \xff\xfe")
        (self.dir / "broken.docx").write_bytes(b"not a zip")
        (self.dir / ".DS_Store").write_bytes(b"noise")
        write_zip(self.dir / "a-policy.docx", {"word/document.xml": DOCX_XML, "word/media/image1.png": b"png"})
        write_zip(self.dir / "b-table.xlsx", {"xl/workbook.xml": WORKBOOK, "xl/_rels/workbook.xml.rels": RELS, "xl/sharedStrings.xml": SHARED,
                                              "xl/styles.xml": STYLES, "xl/worksheets/sheet1.xml": SHEET1, "xl/worksheets/sheet2.xml": SHEET2})
        self.briefs = documents.folder_to_briefs(self.dir)
        self.by_name = dict(self.briefs)

    def test_order_brief_readme_then_path(self):
        self.assertEqual([n for n, _ in self.briefs], ["BRIEF.md", "README.md", "a-policy.docx", "b-table.xlsx", "bad.pdf", "broken.docx", "flow.png", "x.bin", "zzz.txt", "sub/c.md"])

    def test_markdown_and_text_pass_through(self):
        self.assertEqual(self.by_name["BRIEF.md"], "# Özet\nçğıöşü\n")
        self.assertEqual(self.by_name["zzz.txt"], "BOM'lu metin\n")
        self.assertEqual(self.by_name["sub/c.md"], "alt klasör\n")

    def test_docx(self):
        text = self.by_name["a-policy.docx"]
        self.assertTrue(text.startswith("# Document: a-policy.docx\n\n# Gecikme Politikası\nMüşteri çğıöşü harflerini görür.\n\n- İlk madde\n"), text)
        self.assertIn("| Bant | Gün |\n| --- | --- |\n| erken | 1-7 gün |\nSon paragraf.\nimage: image1.png\n", text)
        self.assertNotIn("\n\n\n", text)

    def test_xlsx(self):
        text = self.by_name["b-table.xlsx"]
        self.assertTrue(text.startswith("# Document: b-table.xlsx\n\n## Tatiller\n\n| Tarih | Açıklama |  |\n| --- | --- | --- |\n"), text)
        self.assertIn("| 2026-10-29 | Cumhuriyet Bayramı |  |\n| 42 |  | satır içi |\n\n## Bantlar\n\n| erken | 7 |\n| --- | --- |\n", text)

    def test_xlsx_without_shared_strings(self):
        write_zip(self.dir / "plain.xlsx", {"xl/workbook.xml": WORKBOOK, "xl/_rels/workbook.xml.rels": RELS, "xl/worksheets/sheet1.xml": SHEET2, "xl/worksheets/sheet2.xml": SHEET2})
        text = dict(documents.folder_to_briefs(self.dir))["plain.xlsx"]
        self.assertIn("## Tatiller\n\n| erken | 7 |\n| --- | --- |\n\n## Bantlar\n\n| erken | 7 |\n| --- | --- |\n", text)

    def test_pdf_garbage_does_not_raise(self):
        self.assertEqual(self.by_name["bad.pdf"], "# Document: bad.pdf\n\npdf not readable: bad.pdf")

    def test_images_unknown_and_broken_files(self):
        self.assertEqual(self.by_name["flow.png"], "image file: flow.png")
        self.assertEqual(self.by_name["x.bin"], "skipped: x.bin")
        self.assertTrue(self.by_name["broken.docx"].startswith("# Document: broken.docx\n\nnot readable: broken.docx"))
        self.assertNotIn(".DS_Store", self.by_name)

    def test_image_paths(self):
        self.assertEqual(documents.image_paths(self.dir), [str((self.dir / "flow.png").resolve())])

    def test_deterministic_and_missing_folder(self):
        self.assertEqual(self.briefs, documents.folder_to_briefs(self.dir))
        self.assertEqual(documents.folder_to_briefs(self.dir / "nope"), [])
        self.assertEqual(documents.image_paths(self.dir / "nope"), [])

    def test_real_docx_from_textutil(self):
        if not shutil.which("textutil"):
            self.skipTest("textutil only exists on macOS")
        src = self.dir / "gercek.txt"
        src.write_text("Başlık satırı\n\nİkinci paragraf: çğıöşü ÇĞİÖŞÜ.\n", encoding="utf-8")
        subprocess.run(["textutil", "-convert", "docx", str(src), "-output", str(self.dir / "gercek.docx")], check=True, capture_output=True)
        text = dict(documents.folder_to_briefs(self.dir))["gercek.docx"]
        self.assertIn("Başlık satırı", text); self.assertIn("İkinci paragraf: çğıöşü ÇĞİÖŞÜ.", text)


if __name__ == "__main__":
    unittest.main()
