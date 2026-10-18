"""Conservative parser for labelled fields and three supported line-item layouts."""

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber
from pydantic import ValidationError

from ..schemas import Extraction, LineItem, Source, SourceLimitation
from .classification import keyword_classify
from .review_state import limitation


class PDFError(ValueError):
    pass


class OCRRequired(PDFError):
    pass


def validate_pdf(path: Path, max_pages: int):
    try:
        with pdfplumber.open(path) as pdf:
            if not 1 <= len(pdf.pages) <= max_pages:
                raise PDFError(f"PDF must contain 1–{max_pages} pages")
            # Parse the first page rather than trusting an extension or MIME header.
            pdf.pages[0].extract_text()
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError("Invalid, encrypted, or unreadable PDF") from exc


def number(value: str | None) -> Decimal | None:
    if not value or value.strip().lower() in {"?", "unknown", "n/a", "-", ""}:
        return None
    cleaned = value.strip()
    if cleaned[0] in "₹$€":
        cleaned = cleaned[1:].strip()
    # Only remove separators after checking the grouping; 12,34 must not become 1234.
    plain = r"[0-9]+(?:\.[0-9]+)?"
    western = r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?"
    indian = r"[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3}(?:\.[0-9]+)?"
    if not any(re.fullmatch(pattern, cleaned) for pattern in (plain, western, indian)):
        return None
    try:
        result = Decimal(cleaned.replace(",", ""))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


FIELD_PATTERNS = {
    "document_number": r"(?:Document (?:number|no)|Invoice (?:number|no)|PO (?:number|no)|Quote (?:number|no))\s*[:#]\s*(.+)",
    "order_reference": r"(?:Order reference|Order ref|Reference|PO reference)\s*[:#]\s*(.+)",
    "supplier": r"(?:Supplier|Vendor|From)\s*:\s*(.+)",
    "customer": r"(?:Customer|Buyer|Bill to)\s*:\s*(.+)",
    "currency": r"Currency\s*:\s*([A-Z]{3})",
    "date": r"(?:Date|Issued on)\s*:\s*(.+)",
    "subtotal": r"(?:Subtotal|Net amount)\s*:\s*([\d,.?\-]+)",
    "tax": r"(?:Tax|GST amount)\s*:\s*([\d,.?\-]+)",
    "tax_rate": r"(?:Tax rate|GST rate)\s*:\s*([\d.]+)\s*%?",
    "total": r"(?:Total|Grand total|Amount due)\s*:\s*([\d,.?\-]+)",
}


def parse_line(line: str, source: Source) -> LineItem | None:
    if line.lower().startswith("item:"):
        parts = dict(re.findall(r"([\w ]+)\s*:\s*([^|]+)", line))
        parts = {k.strip().lower(): v.strip() for k, v in parts.items()}
        if "item" not in parts:
            return None
        return LineItem(
            sku=parts.get("sku"),
            description=parts["item"],
            quantity=number(parts.get("qty")),
            unit=None
            if (parts.get("unit") or "").strip().lower() in {"", "?", "unknown", "n/a", "na", "-"}
            else parts["unit"],
            unit_price=number(parts.get("price")),
            amount=number(parts.get("amount")),
            source=source,
        )
    if "|" in line:
        raw = [part.strip() for part in line.split("|")]
        if len(raw) == 6 and raw[0].lower() not in {"sku", "code", "description"}:
            return LineItem(
                sku=raw[0],
                description=raw[1],
                quantity=number(raw[2]),
                unit=None if raw[3] == "?" else raw[3],
                unit_price=number(raw[4]),
                amount=number(raw[5]),
                source=source,
            )
        return None
    # Plain space-delimited table: unambiguous numeric tail anchors each row.
    match = re.fullmatch(
        r"([A-Z][A-Z0-9-]+)\s+(.+?)\s+(\d+(?:\.\d+)?|\?)\s+(m|metres|meters|pcs|pieces|kg|hours|hr|\?)\s+([\d,.]+|\?)\s+([\d,.]+|\?)",
        line,
        re.I,
    )
    if match:
        sku, description, qty, unit, price, amount = match.groups()
        return LineItem(
            sku=sku,
            description=description,
            quantity=number(qty),
            unit=None if unit == "?" else unit,
            unit_price=number(price),
            amount=number(amount),
            source=source,
        )
    return None


def add_source_warning(extraction, source, kind, message):
    warning = SourceLimitation.model_validate(
        limitation(source.document_id, kind, message, source.page)
    )
    if warning not in extraction.source_warnings:
        extraction.source_warnings.append(warning)
        extraction.warnings.append(message)


def parse_field_value(field, raw):
    if raw.lower() in {"?", "unknown", "n/a", "-"}:
        return None
    if field in {"subtotal", "tax", "tax_rate", "total"}:
        value = number(raw)
        if value is None:
            raise ValueError("Unsupported number format")
    elif field == "currency":
        value = raw.upper()
    else:
        value = raw
    # Apply the same limits to extracted values and manually submitted values.
    validated = Extraction(**{field: value})
    return getattr(validated, field)


def read_fields(extraction, line, source):
    for field, pattern in FIELD_PATTERNS.items():
        match = re.fullmatch(pattern, line, re.I)
        if not match:
            continue
        try:
            value = parse_field_value(field, match.group(1).strip())
        except ValueError:
            value = None
            add_source_warning(
                extraction,
                source,
                "invalid_field",
                f"Invalid {field} on page {source.page}; review the source",
            )
        previous = getattr(extraction, field)
        conflict_message = f"Conflicting {field} values; review the source"
        if previous is not None and value != previous:
            setattr(extraction, field, None)
            if conflict_message not in extraction.warnings:
                extraction.warnings.append(conflict_message)
        elif conflict_message not in extraction.warnings:
            setattr(extraction, field, value)
        extraction.sources[field] = source


def read_line_item(extraction, line, source):
    try:
        item = parse_line(line, source)
    except ValidationError:
        add_source_warning(
            extraction,
            source,
            "invalid_row",
            f"Unsupported line item on page {source.page}; review the source",
        )
        return
    if item is None:
        return
    if len(extraction.line_items) >= 200:
        add_source_warning(
            extraction,
            source,
            "row_limit",
            "Only the first 200 supported rows were extracted; review omitted rows",
        )
        return
    extraction.line_items.append(item)


def check_fields(extraction, document_id):
    for field in ("document_number", "currency", "subtotal", "total"):
        if getattr(extraction, field) is None:
            extraction.warnings.append(f"Missing or uncertain {field.replace('_', ' ')}")
    if extraction.document_type == "unknown":
        extraction.warnings.append("Document type requires human review")
    if not extraction.line_items:
        extraction.warnings.append("No supported line-item table found")
        extraction.source_warnings.append(
            SourceLimitation.model_validate(
                limitation(document_id, "incomplete_table", "No supported line-item table found")
            )
        )
    for item in extraction.line_items:
        if any(
            getattr(item, field) is None for field in ("quantity", "unit", "unit_price", "amount")
        ):
            extraction.warnings.append(f"Incomplete line item: {item.description}")


def parse_pages(pages: list[dict], document_id: str) -> dict:
    text = "\n".join(page["text"] for page in pages)
    extraction = Extraction(document_type=keyword_classify(text))
    for page in pages:
        for line in page["text"].splitlines():
            source = Source(document_id=document_id, page=page["number"], snippet=line)
            read_fields(extraction, line, source)
            read_line_item(extraction, line, source)
    check_fields(extraction, document_id)
    return extraction.model_dump(mode="json")


def extract_pdf(path: Path, document_id: str, max_pages: int) -> tuple[dict, list[dict]]:
    validate_pdf(path, max_pages)
    with pdfplumber.open(path) as pdf:
        pages = [
            {"number": i + 1, "text": page.extract_text(x_tolerance=2) or ""}
            for i, page in enumerate(pdf.pages)
        ]
        if sum(len(re.sub(r"\W", "", p["text"])) for p in pages) < 20:
            raise OCRRequired("OCR required: this PDF has no usable selectable text")
        extraction = parse_pages(pages, document_id)
        sources = [
            *extraction["sources"].values(),
            *[item["source"] for item in extraction["line_items"] if item["source"]],
        ]
        for source in sources:
            matches = pdf.pages[source["page"] - 1].search(source["snippet"], regex=False)
            # Only an exact, unique text match warrants a bounding box.
            if len(matches) == 1:
                source["bbox"] = [float(matches[0][key]) for key in ("x0", "top", "x1", "bottom")]
    for page in pages:
        if len(re.sub(r"\W", "", page["text"])) < 20:
            warning = limitation(
                document_id,
                "ocr_page",
                f"Page {page['number']} has no usable text; OCR required or explicit manual source review",
                page["number"],
            )
            extraction["source_warnings"].append(warning)
            extraction["warnings"].append(warning["message"])
    return extraction, pages
