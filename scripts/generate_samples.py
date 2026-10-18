"""Generate fictional, labelled procurement PDFs in three layout families."""

import copy
import json
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample_data"


def base(kind):
    return {
        "document_type": kind,
        "document_number": "PO-1001" if kind == "purchase_order" else "INV-2001",
        "order_reference": "ORDER-001",
        "supplier": "Copperleaf Supply (Fictional)",
        "customer": "Northstar Labs (Fictional)",
        "currency": "INR",
        "date": "2026-01-15",
        "line_items": [
            {
                "sku": "CBL-01",
                "description": "Copper cable",
                "quantity": "100",
                "unit": "m",
                "unit_price": "80",
                "amount": "8000",
            }
        ],
        "subtotal": "8000",
        "tax": "0",
        "tax_rate": "0",
        "total": "8000",
    }


def totals(data):
    for item in data["line_items"]:
        item["amount"] = str(Decimal(item["quantity"]) * Decimal(item["unit_price"]))
    data["subtotal"] = str(sum(Decimal(item["amount"]) for item in data["line_items"]))
    data["total"] = data["subtotal"]


def render_pdf(path: Path, data: dict, layout: str):
    if path.exists():
        return
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    pdf.setTitle(f"Synthetic sample — {data['document_type']}")
    pdf.setFillColor(colors.HexColor("#173b32"))
    pdf.rect(0, height - 85, width, 85, fill=True, stroke=False)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 21)
    heading = {
        "purchase_order": "PURCHASE ORDER",
        "invoice": "INVOICE",
        "quotation": "SUPPLIER QUOTATION",
    }[data["document_type"]]
    pdf.drawString(40, height - 43, heading)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        40, height - 65, "SYNTHETIC SAMPLE — FICTIONAL COMPANIES — NOT A REAL TRANSACTION"
    )
    pdf.setFillColor(colors.HexColor("#263b30"))
    y = height - 116
    # Layout B changes label aliases and field ordering; C uses labelled item cards.
    order = ["document_number", "order_reference", "supplier", "customer", "currency", "date"]
    if layout == "table":
        order = ["supplier", "customer", "date", "currency", "document_number", "order_reference"]
    labels = {
        "document_number": "Document number",
        "order_reference": "Order reference",
        "supplier": "Supplier",
        "customer": "Customer",
        "currency": "Currency",
        "date": "Date",
    }
    if layout == "table":
        labels.update(
            {
                "supplier": "Vendor",
                "customer": "Bill to",
                "date": "Issued on",
                "order_reference": "PO reference",
            }
        )
    pdf.setFont("Helvetica", 10)
    for field in order:
        if data.get(field) is not None:
            pdf.drawString(40, y, f"{labels[field]}: {data[field]}")
            y -= 21
    y -= 20
    pdf.setFont("Helvetica-Bold", 9)
    if layout == "pipe":
        pdf.drawString(40, y, "SKU | Description | Quantity | Unit | Unit price | Amount")
    elif layout == "table":
        for x, title in zip(
            [40, 103, 278, 335, 388, 475],
            ["Code", "Description", "Quantity", "Unit", "Price", "Amount"],
        ):
            pdf.drawString(x, y, title)
    else:
        pdf.drawString(40, y, "ORDERED GOODS / REVIEW DETAILS")
    y -= 26
    pdf.setFont("Helvetica", 9)
    for item in data["line_items"]:
        values = [
            item.get(k) if item.get(k) is not None else "?"
            for k in ("sku", "description", "quantity", "unit", "unit_price", "amount")
        ]
        if layout == "pipe":
            pdf.drawString(40, y, " | ".join(values))
        elif layout == "table":
            for x, value in zip([40, 103, 278, 335, 388, 475], values):
                pdf.drawString(x, y, value)
        else:
            pdf.setFont("Helvetica", 8)
            pdf.drawString(
                40,
                y,
                f"Item: {values[1]} | SKU: {values[0]} | Qty: {values[2]} | Unit: {values[3]} | Price: {values[4]} | Amount: {values[5]}",
            )
        y -= 28
    y -= 30
    pdf.setFont("Helvetica", 10)
    for field, label in (
        ("subtotal", "Net amount" if layout == "table" else "Subtotal"),
        ("tax_rate", "Tax rate"),
        ("tax", "GST amount" if layout == "table" else "Tax"),
        ("total", "Amount due" if layout == "table" else "Total"),
    ):
        value = data.get(field)
        if value is not None:
            pdf.drawString(40, y, f"{label}: {value}{'%' if field == 'tax_rate' else ''}")
            y -= 21
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(
        40, 35, "DocVerify demo | Selectable text | Source values are intentionally varied"
    )
    pdf.save()


def generate():
    OUT.mkdir(exist_ok=True)
    cases, documents = [], []
    specs = [
        ("matching", "01 · Matching order & invoice", []),
        ("quantity", "02 · Quantity difference", ["quantity_difference", "subtotal_difference"]),
        ("price", "03 · Unit-price difference", ["unit_price_difference", "subtotal_difference"]),
        (
            "both",
            "04 · Quantity + price (INR 2,200)",
            ["quantity_difference", "unit_price_difference", "subtotal_difference"],
        ),
        (
            "arithmetic",
            "05 · Arithmetic error & missing item",
            ["arithmetic_error", "missing_item", "subtotal_difference"],
        ),
        (
            "incomplete",
            "06 · Incomplete & ambiguous data",
            ["extraction_uncertainty", "missing_identifier", "ambiguous_match"],
        ),
        (
            "incompatible",
            "07 · Currency & unit incompatibility",
            ["currency_incompatible", "unit_incompatible"],
        ),
    ]
    for index, (slug, name, expected) in enumerate(specs):
        po, invoice = base("purchase_order"), base("invoice")
        if slug in {"quantity", "both"}:
            invoice["line_items"][0]["quantity"] = "120"
            totals(invoice)
        if slug in {"price", "both"}:
            invoice["line_items"][0]["unit_price"] = "85"
            totals(invoice)
        if slug == "arithmetic":
            po["line_items"].append(
                {
                    "sku": "CON-02",
                    "description": "Cable connector",
                    "quantity": "10",
                    "unit": "pcs",
                    "unit_price": "20",
                    "amount": "200",
                }
            )
            totals(po)
            invoice["line_items"][0]["amount"] = "8100"
            invoice["subtotal"] = invoice["total"] = "8100"
        if slug == "incomplete":
            invoice["document_number"] = None
            invoice["line_items"][0]["quantity"] = None
            invoice["line_items"].append(copy.deepcopy(invoice["line_items"][0]))
        if slug == "incompatible":
            invoice["currency"] = "USD"
            invoice["line_items"][0]["unit"] = "pcs"
        files = []
        for kind, data, layout in [
            ("po", po, ["pipe", "table", "cards"][index % 3]),
            ("invoice", invoice, ["table", "cards", "pipe"][index % 3]),
        ]:
            filename = f"{slug}_{kind}.pdf"
            render_pdf(OUT / filename, data, layout)
            files.append(filename)
            documents.append({"file": filename, "family": layout, "expected": data})
        cases.append({"name": name, "files": files, "expected_finding_types": expected})
    # Include a standalone quotation to demonstrate all classification labels.
    quote = base("quotation")
    quote["document_number"] = "QT-3001"
    render_pdf(OUT / "sample_quotation.pdf", quote, "cards")
    documents.append({"file": "sample_quotation.pdf", "family": "cards", "expected": quote})
    manifest = {
        "synthetic": True,
        "layout_families": ["pipe", "table", "cards"],
        "cases": cases,
        "documents": documents,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    queries = [
        {
            "query": "PO-1001 purchase order",
            "relevant_files": [
                d["file"] for d in documents if d["expected"]["document_type"] == "purchase_order"
            ],
        },
        {
            "query": "INV-2001 invoice",
            "relevant_files": [
                d["file"]
                for d in documents
                if d["expected"]["document_type"] == "invoice" and d["expected"]["document_number"]
            ],
        },
        {"query": "QT-3001 supplier quotation", "relevant_files": ["sample_quotation.pdf"]},
        {"query": "Cable connector CON-02", "relevant_files": ["arithmetic_po.pdf"]},
        {"query": "Currency USD", "relevant_files": ["incompatible_invoice.pdf"]},
        {"query": "What is the supplier bank IBAN?", "relevant_files": [], "unanswerable": True},
        {"query": "Warranty expiration date", "relevant_files": [], "unanswerable": True},
        {"query": "Shipment tracking AWB", "relevant_files": [], "unanswerable": True},
    ]
    (ROOT / "evaluation/retrieval_queries.json").write_text(json.dumps(queries, indent=2))
    print(f"Generated {len(documents)} synthetic PDFs and {len(cases)} demo cases")


if __name__ == "__main__":
    generate()
