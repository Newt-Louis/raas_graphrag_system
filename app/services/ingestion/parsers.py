from __future__ import annotations

import csv
import hashlib
import html.parser
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from app.services.ingestion.models import (
    DocumentScope,
    ElementType,
    ParsedDocument,
    SourceFile,
    StructuralElement,
)


ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".txt",
    ".md",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".jsonl",
}

BLOCKED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
    ".heic",
    ".avif",
}

BLOCKED_IMAGE_CONTENT_PREFIX = "image/"

_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
_PRESENTATION_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
_SHEET_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class DocumentValidationError(ValueError):
    pass


class ParserUnavailableError(RuntimeError):
    pass


def validate_document_file(filename: str, content_type: str | None = None) -> str:
    extension = Path(filename).suffix.lower()
    if extension in BLOCKED_IMAGE_EXTENSIONS or (
        content_type and content_type.lower().startswith(BLOCKED_IMAGE_CONTENT_PREFIX)
    ):
        raise DocumentValidationError("Image uploads are not accepted as source documents.")
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))
        raise DocumentValidationError(f"Unsupported document extension '{extension}'. Allowed: {allowed}")
    return extension


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class BaseParser:
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        raise NotImplementedError

    def _element(
        self,
        source: SourceFile,
        order: int,
        element_type: ElementType,
        text: str = "",
        **kwargs: object,
    ) -> StructuralElement:
        return StructuralElement(
            element_id=f"{source.document_id}:el:{order}",
            element_type=element_type,
            text=text.strip(),
            order=order,
            **kwargs,
        )


class TextParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        text = path.read_text(encoding="utf-8", errors="replace")
        elements: list[StructuralElement] = []
        order = 0
        for block in re.split(r"\n\s*\n", text):
            stripped = block.strip()
            if not stripped:
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if source.extension == ".md" and heading:
                elements.append(
                    self._element(
                        source,
                        order,
                        ElementType.HEADING,
                        heading.group(2),
                        level=len(heading.group(1)),
                    )
                )
            else:
                element_type = ElementType.CODE if stripped.startswith("```") else ElementType.PARAGRAPH
                elements.append(self._element(source, order, element_type, stripped))
            order += 1

        title = elements[0].text if elements and elements[0].element_type == ElementType.HEADING else path.stem
        return ParsedDocument(scope=scope, source=source, title=title, elements=elements)


class CsvParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = [[cell.strip() for cell in row] for row in csv.reader(handle)]
        elements = [
            self._element(
                source,
                0,
                ElementType.TABLE,
                table=rows,
                metadata={"row_count": len(rows), "column_count": max((len(row) for row in rows), default=0)},
            )
        ]
        return ParsedDocument(scope=scope, source=source, title=path.stem, elements=elements)


class JsonParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        if source.extension == ".jsonl":
            elements = []
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for order, line in enumerate(handle):
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    elements.append(
                        self._element(
                            source,
                            order,
                            ElementType.JSON_RECORD,
                            json.dumps(value, ensure_ascii=False, sort_keys=True),
                            metadata={"jsonl_line": order + 1},
                        )
                    )
            return ParsedDocument(scope=scope, source=source, title=path.stem, elements=elements)

        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        elements = [self._element(source, 0, ElementType.JSON_RECORD, text)]
        return ParsedDocument(scope=scope, source=source, title=path.stem, elements=elements)


class _StructureHtmlParser(html.parser.HTMLParser):
    def __init__(self, source: SourceFile):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.elements: list[StructuralElement] = []
        self._tag_stack: list[str] = []
        self._text_parts: list[str] = []
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._order = 0
        self.title: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._flush_if_block_boundary(tag)
        self._tag_stack.append(tag)
        if tag == "tr":
            self._current_row = []
        if tag == "img":
            attr_map = {key.lower(): value for key, value in attrs if value is not None}
            alt_text = attr_map.get("alt", "")
            src = attr_map.get("src", "")
            self._add(ElementType.IMAGE, alt_text, image_ref=src, metadata={"alt_text": alt_text})

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "code"}:
            text = self._consume_text()
            if text:
                if tag.startswith("h"):
                    level = int(tag[1])
                    self.title = self.title or text
                    self._add(ElementType.HEADING, text, level=level)
                elif tag == "li":
                    self._add(ElementType.LIST_ITEM, text)
                elif tag in {"pre", "code"}:
                    self._add(ElementType.CODE, text)
                else:
                    self._add(ElementType.PARAGRAPH, text)
        elif tag in {"td", "th"}:
            self._current_row.append(self._consume_text())
        elif tag == "tr" and self._current_row:
            self._table_rows.append(self._current_row)
            self._current_row = []
        elif tag == "table" and self._table_rows:
            self._add(ElementType.TABLE, table=self._table_rows)
            self._table_rows = []

        if tag in self._tag_stack:
            self._tag_stack.remove(tag)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._text_parts.append(data)

    def _flush_if_block_boundary(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr", "table"}:
            self._text_parts = []

    def _consume_text(self) -> str:
        text = " ".join(part.strip() for part in self._text_parts if part.strip())
        self._text_parts = []
        return text

    def _add(
        self,
        element_type: ElementType,
        text: str = "",
        table: list[list[str]] | None = None,
        image_ref: str | None = None,
        level: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.elements.append(
            StructuralElement(
                element_id=f"{self.source.document_id}:el:{self._order}",
                element_type=element_type,
                text=text.strip(),
                order=self._order,
                level=level,
                table=table,
                image_ref=image_ref,
                metadata=dict(metadata or {}),
            )
        )
        self._order += 1


class HtmlDocumentParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        parser = _StructureHtmlParser(source)
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        return ParsedDocument(scope=scope, source=source, title=parser.title or path.stem, elements=parser.elements)


class DocxParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
            root = ET.fromstring(document_xml)
            elements: list[StructuralElement] = []
            order = 0
            for child in root.findall(".//w:body/*", _WORD_NS):
                tag = _strip_namespace(child.tag)
                if tag == "p":
                    text = _join_xml_text(child.findall(".//w:t", _WORD_NS))
                    if not text:
                        continue
                    style = child.find(".//w:pStyle", _WORD_NS)
                    style_value = style.attrib.get(f"{{{_WORD_NS['w']}}}val", "") if style is not None else ""
                    heading_match = re.match(r"Heading([1-6])", style_value)
                    element_type = ElementType.HEADING if heading_match else ElementType.PARAGRAPH
                    level = int(heading_match.group(1)) if heading_match else None
                    elements.append(self._element(source, order, element_type, text, level=level))
                    order += 1
                elif tag == "tbl":
                    table = []
                    for row in child.findall(".//w:tr", _WORD_NS):
                        table.append([
                            _join_xml_text(cell.findall(".//w:t", _WORD_NS))
                            for cell in row.findall("./w:tc", _WORD_NS)
                        ])
                    elements.append(self._element(source, order, ElementType.TABLE, table=table))
                    order += 1

            for image_name in _zip_media_paths(archive, "word/media/"):
                elements.append(
                    self._element(
                        source,
                        order,
                        ElementType.IMAGE,
                        image_ref=image_name,
                        metadata={"embedded": True, "container": "docx"},
                    )
                )
                order += 1

        title = next((element.text for element in elements if element.element_type == ElementType.HEADING), path.stem)
        return ParsedDocument(scope=scope, source=source, title=title, elements=elements)


class PptxParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        with zipfile.ZipFile(path) as archive:
            elements: list[StructuralElement] = []
            order = 0
            slide_paths = sorted(
                [name for name in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)],
                key=_natural_key,
            )
            for slide_index, slide_path in enumerate(slide_paths, start=1):
                elements.append(self._element(source, order, ElementType.SLIDE, f"Slide {slide_index}", slide_number=slide_index))
                order += 1
                root = ET.fromstring(archive.read(slide_path))
                texts = [
                    _join_xml_text(paragraph.findall(".//a:t", _PRESENTATION_NS))
                    for paragraph in root.findall(".//a:p", _PRESENTATION_NS)
                ]
                for text in [item for item in texts if item.strip()]:
                    elements.append(
                        self._element(
                            source,
                            order,
                            ElementType.PARAGRAPH,
                            text,
                            slide_number=slide_index,
                        )
                    )
                    order += 1

            for image_name in _zip_media_paths(archive, "ppt/media/"):
                elements.append(
                    self._element(
                        source,
                        order,
                        ElementType.IMAGE,
                        image_ref=image_name,
                        metadata={"embedded": True, "container": "pptx"},
                    )
                )
                order += 1

        return ParsedDocument(scope=scope, source=source, title=path.stem, elements=elements)


class XlsxParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        with zipfile.ZipFile(path) as archive:
            shared_strings = self._shared_strings(archive)
            sheet_names = self._sheet_names(archive)
            sheet_paths = sorted(
                [name for name in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name)],
                key=_natural_key,
            )
            elements: list[StructuralElement] = []
            order = 0
            for sheet_index, sheet_path in enumerate(sheet_paths, start=1):
                sheet_name = sheet_names.get(sheet_index, f"Sheet {sheet_index}")
                elements.append(self._element(source, order, ElementType.SHEET, sheet_name, sheet_name=sheet_name))
                order += 1
                table = self._sheet_table(archive, sheet_path, shared_strings)
                if table:
                    elements.append(
                        self._element(
                            source,
                            order,
                            ElementType.TABLE,
                            sheet_name=sheet_name,
                            table=table,
                            metadata={"row_count": len(table), "sheet_path": sheet_path},
                        )
                    )
                    order += 1

            for image_name in _zip_media_paths(archive, "xl/media/"):
                elements.append(
                    self._element(
                        source,
                        order,
                        ElementType.IMAGE,
                        image_ref=image_name,
                        metadata={"embedded": True, "container": "xlsx"},
                    )
                )
                order += 1

        return ParsedDocument(scope=scope, source=source, title=path.stem, elements=elements)

    def _shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        return [_join_xml_text(item.findall(".//main:t", _SHEET_NS)) for item in root.findall(".//main:si", _SHEET_NS)]

    def _sheet_names(self, archive: zipfile.ZipFile) -> dict[int, str]:
        if "xl/workbook.xml" not in archive.namelist():
            return {}
        root = ET.fromstring(archive.read("xl/workbook.xml"))
        names: dict[int, str] = {}
        for index, sheet in enumerate(root.findall(".//main:sheet", _SHEET_NS), start=1):
            names[index] = sheet.attrib.get("name", f"Sheet {index}")
        return names

    def _sheet_table(
        self,
        archive: zipfile.ZipFile,
        sheet_path: str,
        shared_strings: list[str],
    ) -> list[list[str]]:
        root = ET.fromstring(archive.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.findall(".//main:row", _SHEET_NS):
            values = []
            for cell in row.findall("./main:c", _SHEET_NS):
                cell_type = cell.attrib.get("t")
                raw_value = cell.findtext("./main:v", default="", namespaces=_SHEET_NS)
                if cell_type == "s" and raw_value.isdigit():
                    index = int(raw_value)
                    values.append(shared_strings[index] if index < len(shared_strings) else "")
                elif cell_type == "inlineStr":
                    values.append(_join_xml_text(cell.findall(".//main:t", _SHEET_NS)))
                else:
                    values.append(raw_value)
            if any(value.strip() for value in values):
                rows.append(values)
        return rows


class PdfParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        try:
            from pypdf import PdfReader
        except ModuleNotFoundError as exc:
            raise ParserUnavailableError(
                "PDF parsing requires the optional 'pypdf' package. Install project requirements before ingesting PDFs."
            ) from exc

        reader = PdfReader(str(path))
        elements: list[StructuralElement] = []
        order = 0
        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                elements.append(
                    self._element(
                        source,
                        order,
                        ElementType.PARAGRAPH,
                        text,
                        page_number=page_index,
                        metadata={"page_number": page_index},
                    )
                )
                order += 1
            images = getattr(page, "images", [])
            for image_index, image in enumerate(images, start=1):
                image_name = getattr(image, "name", f"page-{page_index}-image-{image_index}")
                elements.append(
                    self._element(
                        source,
                        order,
                        ElementType.IMAGE,
                        page_number=page_index,
                        image_ref=image_name,
                        metadata={"embedded": True, "container": "pdf", "page_number": page_index},
                    )
                )
                order += 1

        return ParsedDocument(scope=scope, source=source, title=path.stem, elements=elements)


class UnsupportedLegacyOfficeParser(BaseParser):
    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        raise ParserUnavailableError(
            f"'{source.extension}' is accepted by policy, but binary Office parsing needs a converter/parser adapter. "
            "Use .docx/.pptx/.xlsx for the built-in parser, or add a LibreOffice/Apache Tika adapter."
        )


class DocumentParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {
            ".txt": TextParser(),
            ".md": TextParser(),
            ".csv": CsvParser(),
            ".json": JsonParser(),
            ".jsonl": JsonParser(),
            ".html": HtmlDocumentParser(),
            ".htm": HtmlDocumentParser(),
            ".docx": DocxParser(),
            ".pptx": PptxParser(),
            ".xlsx": XlsxParser(),
            ".pdf": PdfParser(),
            ".doc": UnsupportedLegacyOfficeParser(),
            ".ppt": UnsupportedLegacyOfficeParser(),
            ".xls": UnsupportedLegacyOfficeParser(),
        }

    def parse(self, path: Path, scope: DocumentScope, source: SourceFile) -> ParsedDocument:
        parser = self._parsers.get(source.extension)
        if parser is None:
            raise DocumentValidationError(f"No parser registered for extension '{source.extension}'.")
        return parser.parse(path, scope, source)


def _join_xml_text(nodes: Iterable[ET.Element]) -> str:
    return "".join(node.text or "" for node in nodes).strip()


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _zip_media_paths(archive: zipfile.ZipFile, prefix: str) -> list[str]:
    return sorted(name for name in archive.namelist() if name.startswith(prefix) and not name.endswith("/"))


def _natural_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]
