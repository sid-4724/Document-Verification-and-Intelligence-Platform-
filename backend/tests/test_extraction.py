import io

from app.services.extraction import extract_pdf, parse_pages
from reportlab.pdfgen import canvas


def test_second_page_provenance_and_reliable_coordinates(tmp_path):
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    for i, line in enumerate(
        ["INVOICE", "Document number: INV-2", "Order reference: REF-2", "Currency: INR"]
    ):
        pdf.drawString(40, 750 - 22 * i, line)
    pdf.showPage()
    for i, line in enumerate(
        [
            "SKU | Description | Quantity | Unit | Unit price | Amount",
            "CBL-1 | Copper cable | 2 | m | 80 | 160",
            "Subtotal: 160",
            "Tax: 0",
            "Total: 160",
        ]
    ):
        pdf.drawString(40, 750 - 22 * i, line)
    pdf.save()
    path = tmp_path / "multipage.pdf"
    path.write_bytes(output.getvalue())
    data, pages = extract_pdf(path, "document-2", 30)
    assert len(pages) == 2
    assert data["line_items"][0]["source"]["page"] == 2
    assert data["sources"]["subtotal"]["page"] == 2
    assert data["sources"]["subtotal"]["document_id"] == "document-2"
    assert len(data["sources"]["subtotal"]["bbox"]) == 4


def test_conflicting_fields_are_unknown():
    data = parse_pages(
        [{"number": 1, "text": "INVOICE\nSubtotal: 100\nSubtotal: 200\nSubtotal: 100"}], "doc"
    )
    assert data["subtotal"] is None
    assert any("Conflicting subtotal" in warning for warning in data["warnings"])


def test_unknown_numeric_value_is_not_invented():
    data = parse_pages(
        [{"number": 1, "text": "INVOICE\nSubtotal: ?\nA1 | Cable | ? | m | 0 | 0"}], "doc"
    )
    assert data["subtotal"] is None
    assert data["line_items"][0]["quantity"] is None
    assert data["line_items"][0]["amount"] == "0"
