"""A folder of a bank's documents (Markdown, Word, Excel, PDF, images) as Markdown text for the normalize stage.

Standard library only: zipfile and xml.etree read .docx and .xlsx; a PDF is read with pypdf or the pdftotext command
when present and otherwise reported as unreadable. Nothing raises on a broken file: the build must reach normalize.
"""
import datetime
import pathlib
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
TEXT = (".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml")     # a service contract may come as OpenAPI JSON or YAML
IMAGES = (".png", ".jpg", ".jpeg", ".svg", ".gif")
FIRST = ("brief.md", "readme.md")
DATE_FORMATS = {14, 15, 16, 17, 22}  # Excel's built-in date formats; times and plain numbers are not dates


def folder_to_briefs(folder):
    """Ordered (relative name, markdown) pairs for every file in the folder: BRIEF.md, README.md, then the rest by path."""
    return [(name, document_text(path, name)) for name, path in ordered_files(folder)]


def image_paths(folder):
    """Absolute paths of the image files, in the same order, for a model that can look at a flow drawing."""
    return [str(path.resolve()) for _, path in ordered_files(folder) if path.suffix.lower() in IMAGES]


def ordered_files(folder):
    root = pathlib.Path(folder)
    if not root.is_dir():
        return []
    # the hackathon page says to read BRIEF.md first and README.md second; dotfiles such as .DS_Store are noise
    files = [(p.relative_to(root).as_posix(), p) for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")]
    return sorted(files, key=lambda f: (FIRST.index(f[1].name.lower()) if f[1].name.lower() in FIRST else len(FIRST), f[0].count("/"), f[0]))


def document_text(path, name):
    """Markdown for one file; a converted document starts with a heading naming the source file."""
    kind, head = path.suffix.lower(), "# Document: %s\n\n" % name
    try:
        if kind in TEXT:
            return path.read_bytes().decode("utf-8-sig", errors="replace")
        if kind in IMAGES:
            return "image file: " + name
        if kind == ".docx":
            return head + docx_text(path)
        if kind == ".xlsx":
            return head + xlsx_text(path)
        if kind == ".pdf":
            return head + pdf_text(path, name)
    except Exception as e:  # a corrupt document is reported in the text, never fatal
        return head + "not readable: %s (%s)" % (name, e)
    return "skipped: " + name


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
        media = sorted(n.split("/")[-1] for n in z.namelist() if n.startswith("word/media/"))
    lines = []
    for block in body if body is not None else []:
        if block.tag == W + "p":
            lines.append(paragraph_text(block))
        elif block.tag == W + "tbl":
            lines.append(table_markdown([[cell_text(c) for c in row.findall(W + "tc")] for row in block.findall(W + "tr")]))
    text = "\n".join(lines + ["image: " + m for m in media])
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def paragraph_text(p):
    """A paragraph's text; a Heading style becomes a Markdown heading and a numbered paragraph a list item."""
    parts = []
    for el in p.iter():
        if el.tag == W + "t":
            parts.append(el.text or "")
        elif el.tag in (W + "tab", W + "br"):
            parts.append(" " if el.tag == W + "tab" else "\n")
    text = "".join(parts).strip()
    style = p.find(W + "pPr/" + W + "pStyle")
    style = style.get(W + "val", "") if style is not None else ""
    if text and style.lower().startswith("heading") and style[-1:].isdigit():
        return "#" * int(style[-1]) + " " + text
    if text and p.find(W + "pPr/" + W + "numPr") is not None:
        return "- " + text
    return text


def cell_text(cell):
    return " ".join(t for t in (paragraph_text(p) for p in cell.iter(W + "p")) if t)


def table_markdown(rows):
    rows = [[c.replace("\n", " ").replace("|", "\\|") for c in r] for r in rows if any(c.strip() for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    return "\n".join(out + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def xlsx_text(path):
    with zipfile.ZipFile(path) as z:
        shared, dated = shared_strings(z), date_styles(z)
        parts = ["## " + name + "\n\n" + table_markdown(sheet_rows(ET.fromstring(z.read(target)), shared, dated)) for name, target in sheet_files(z)]
    return "\n\n".join(parts).strip() + "\n"


def sheet_files(z):
    """(sheet name, zip path) pairs in workbook order through the workbook relationships; sheetN.xml files otherwise."""
    names = z.namelist()
    try:
        book = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target", "") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    except (KeyError, ET.ParseError):
        return [(p.split("/")[-1].rsplit(".", 1)[0], p) for p in sorted(n for n in names if n.startswith("xl/worksheets/sheet"))]
    out = []
    for sheet in book.iter(S + "sheet"):
        target = rels.get(sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"), "")
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if target in names:
            out.append((sheet.get("name") or target, target))
    return out


def shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(S + "t")) for si in root.findall(S + "si")]


def date_styles(z):
    """Indices of the cell styles that show a date, because Excel stores a date as a day count."""
    if "xl/styles.xml" not in z.namelist():
        return set()
    root = ET.fromstring(z.read("xl/styles.xml"))
    custom = {f.get("numFmtId"): f.get("formatCode", "").lower() for f in root.iter(S + "numFmt")}
    xfs = root.find(S + "cellXfs")
    dated = set()
    for i, xf in enumerate(xfs.findall(S + "xf") if xfs is not None else []):
        fmt = xf.get("numFmtId", "0")
        if (fmt.isdigit() and int(fmt) in DATE_FORMATS) or ("y" in custom.get(fmt, "") and "d" in custom.get(fmt, "")):
            dated.add(i)
    return dated


def sheet_rows(root, shared, dated):
    rows = []
    for row in root.iter(S + "row"):
        cells = []
        for c in row.findall(S + "c"):  # the cell reference places it in its column, so gaps stay empty cells
            col = column_index(c.get("r", ""))
            cells += [""] * (max(col, len(cells)) - len(cells))
            cells.append(cell_value(c, shared, dated))
        rows.append(cells)
    return rows


def column_index(ref):
    n = 0
    for ch in ref.rstrip("0123456789").upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def cell_value(c, shared, dated):
    kind = c.get("t", "n")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in c.iter(S + "t"))
    v = c.find(S + "v")
    text = (v.text or "") if v is not None else ""
    if kind == "s":
        return shared[int(text)] if text.isdigit() and int(text) < len(shared) else ""
    if kind == "b":
        return "true" if text == "1" else "false"
    if c.get("s", "").isdigit() and int(c.get("s")) in dated and text.replace(".", "", 1).isdigit():
        when = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=float(text))
        return when.strftime("%Y-%m-%d" if when.time() == datetime.time() else "%Y-%m-%d %H:%M")
    return text


def pdf_text(path, name):
    """pypdf when installed, else the pdftotext command, else a note; the builder never installs anything."""
    try:
        import pypdf
        text = "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(str(path)).pages)
    except Exception:
        text = ""
    if not text.strip() and shutil.which("pdftotext"):
        try:
            text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, timeout=60).stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError):
            text = ""
    return text if text.strip() else "pdf not readable: " + name
