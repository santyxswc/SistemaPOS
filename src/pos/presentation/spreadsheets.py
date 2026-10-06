"""Hojas de cálculo: leer CSV o Excel (.xlsx) y escribir Excel, sin dependencias externas.

Es un formato de presentación, como el JSON de la API: los casos de uso reciben y
entregan datos, y aquí se traducen a lo que el dueño del negocio abre con Excel.

- Lectura: .xlsx (primera hoja) o CSV con «;», «,» o tabulador, en UTF-8 o en la
  codificación de Excel para Windows. Las celdas numéricas de Excel llegan como
  Decimal exacto; el texto, tal cual.
- Escritura: .xlsx con encabezado en negrilla, números como números (Excel en
  español los muestra con su separador) y anchos de columna razonables.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree
from xml.sax.saxutils import escape

Cell = str | Decimal | int | date | datetime | None

MAX_ROWS = 20_000
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # un .xlsx es un zip: se limita lo que ocupa al descomprimirlo

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class SpreadsheetError(ValueError):
    """El archivo no se pudo leer como hoja de cálculo."""


# --- lectura -------------------------------------------------------------------------


Row = tuple[int, list[str | Decimal]]  # (número de fila como lo muestra Excel, celdas)


def read_rows(data: bytes, filename: str = "") -> list[Row]:
    """Filas de la primera hoja con su número, sin las filas completamente vacías."""
    if len(data) > MAX_FILE_BYTES:
        raise SpreadsheetError("El archivo es demasiado grande (máximo 10 MB)")
    if data[:2] == b"PK" or filename.lower().endswith(".xlsx"):
        rows = _read_xlsx(data)
    elif filename.lower().endswith(".xls"):
        raise SpreadsheetError("Ese es el formato antiguo de Excel (.xls): guárdelo como .xlsx o .csv")
    else:
        rows = _read_csv(data)
    rows = [(number, cells) for number, cells in rows if any(str(cell).strip() for cell in cells)]
    if len(rows) > MAX_ROWS + 1:
        raise SpreadsheetError(f"El archivo tiene demasiadas filas (máximo {MAX_ROWS:,})".replace(",", "."))
    return rows


def _read_csv(data: bytes) -> list[Row]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 decodifica casi todo
        raise SpreadsheetError("No se reconoce la codificación del archivo")
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [(reader.line_num, list(row)) for row in reader]


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if letters is None:
        raise SpreadsheetError("Celda sin referencia válida")
    index = 0
    for letter in letters.group():
        index = index * 26 + (ord(letter) - 64)
    return index - 1


def _read_xlsx(data: bytes) -> list[Row]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise SpreadsheetError("El archivo de Excel es demasiado grande")
        shared = _shared_strings(archive)
        sheet = ElementTree.fromstring(archive.read(_first_sheet_path(archive)))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise SpreadsheetError("El archivo no es un Excel (.xlsx) válido") from None

    rows: list[Row] = []
    for index, row in enumerate(sheet.iter(f"{_MAIN}row"), start=1):
        values: dict[int, str | Decimal] = {}
        for position, cell in enumerate(row.iter(f"{_MAIN}c")):
            reference = cell.get("r")
            column = _column_index(reference) if reference else position
            values[column] = _cell_value(cell, shared)
        if values:
            number = int(row.get("r") or index)
            rows.append((number, [values.get(i, "") for i in range(max(values) + 1)]))
    return rows


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> str | Decimal:
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{_MAIN}t"))
    raw = cell.findtext(f"{_MAIN}v")
    if raw is None:
        return ""
    if kind == "s":
        return shared[int(raw)]
    if kind == "b":
        return "1" if raw == "1" else "0"
    if kind in ("str", "e"):
        return raw
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return raw
    if number == number.to_integral():
        return number.to_integral()
    return number.quantize(Decimal("0.000001")).normalize()  # Excel guarda 0.1 como 0.10000000000000001


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{_MAIN}t")) for item in root.iter(f"{_MAIN}si")]


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    first = workbook.find(f"{_MAIN}sheets/{_MAIN}sheet")
    if first is None:
        raise KeyError("sin hojas")
    rel_id = first.get(f"{_REL}id")
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.iter(f"{_PKG_REL}Relationship"):
        if rel.get("Id") == rel_id:
            target = rel.get("Target", "")
            return target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    raise KeyError(rel_id)


# --- escritura ------------------------------------------------------------------------

# Estilos: 0 normal, 1 encabezado en negrilla, 2 dinero (#.##0), 3 fecha y hora, 4 decimal.
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="dd/mm/yyyy hh:mm"/>
<numFmt numFmtId="165" formatCode="#,##0.###"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


@dataclass
class Sheet:
    name: str
    header: Sequence[str]
    rows: Iterable[Sequence[Cell]] = field(default_factory=list)
    money_columns: frozenset[int] = frozenset()  # índices con formato de dinero; los demás números, decimales


def _attr(text: str) -> str:
    return escape(text, {'"': "&quot;"})


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _excel_serial(value: date | datetime) -> Decimal:
    """Excel cuenta los días desde el 30/12/1899; la hora es la fracción del día."""
    base = datetime(1899, 12, 30)
    moment = value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time())
    delta = moment.replace(tzinfo=None) - base
    return (Decimal(delta.days) + Decimal(delta.seconds) / Decimal(86_400)).quantize(Decimal("1e-10"))


def _cell_xml(reference: str, value: Cell, style: int) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (date, datetime)):
        return f'<c r="{reference}" s="3"><v>{_excel_serial(value)}</v></c>'
    if isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        number = format(value, "f") if isinstance(value, Decimal) else str(value)  # nunca 4E+1
        return f'<c r="{reference}" s="{style}"><v>{number}</v></c>'
    style_attr = ' s="1"' if style == 1 else ""
    text = escape(str(value))
    return f'<c r="{reference}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(sheet: Sheet) -> str:
    widths = [max(10, min(len(title) + 2, 40)) for title in sheet.header]
    lines = []
    header = "".join(_cell_xml(f"{_column_letter(i)}1", title, 1) for i, title in enumerate(sheet.header))
    lines.append(f'<row r="1">{header}</row>')
    for row_number, row in enumerate(sheet.rows, start=2):
        cells = []
        for i, value in enumerate(row):
            style = 2 if i in sheet.money_columns else 4
            cells.append(_cell_xml(f"{_column_letter(i)}{row_number}", value, style))
            if i < len(widths) and isinstance(value, str):
                widths[i] = max(widths[i], min(len(value) + 2, 60))
        lines.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
        'state="frozen"/></sheetView></sheetViews>'
        f"<cols>{cols}</cols><sheetData>{''.join(lines)}</sheetData></worksheet>"
    )


def write_xlsx(sheets: Sequence[Sheet]) -> bytes:
    """Un libro de Excel con una hoja por elemento de `sheets` (fila 1 fija como encabezado)."""
    buffer = io.BytesIO()
    names = [re.sub(r"[\\/?*\[\]:]", "", sheet.name)[:31] or f"Hoja{i + 1}" for i, sheet in enumerate(sheets)]
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(len(sheets))
        )
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{overrides}</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        sheet_list = "".join(
            f'<sheet name="{_attr(name)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, name in enumerate(names)
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheet_list}</sheets></workbook>",
        )
        rels = "".join(
            f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            f'relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(len(sheets))
        )
        styles_id = len(sheets) + 1
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{rels}<Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/styles" Target="styles.xml"/></Relationships>',
        )
        archive.writestr("xl/styles.xml", _STYLES)
        for i, sheet in enumerate(sheets):
            archive.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet_xml(sheet))
    return buffer.getvalue()


XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
