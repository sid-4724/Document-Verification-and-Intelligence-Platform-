"""Independent-review reproductions; these use disposable fixture data only."""

import copy
import io

from app import worker
from app.main import app
from app.services.verification import verify_documents
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from .test_api_worker import process_all, upload
from .test_verification import document


def test_repeated_unmatched_rows_save_without_duplicate_findings(client, case):
    documents = upload(client, case)
    process_all()
    doc_id = documents[0]["id"]
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    washer = {
        "description": "Washer",
        "sku": None,
        "quantity": "2",
        "unit": "pcs",
        "unit_price": "1",
        "amount": "2",
        "source": None,
    }
    data["line_items"].extend([copy.deepcopy(washer), copy.deepcopy(washer)])
    data["subtotal"] = data["total"] = "8004"
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        safe_client.cookies.update(client.cookies)
        safe_client.headers.update(client.headers)
        response = safe_client.put(f"/api/documents/{doc_id}/correction", json=data)
    assert response.status_code == 200
    findings = client.get(f"/api/cases/{case['id']}/findings").json()
    unmatched = [finding for finding in findings if finding["kind"] == "missing_item"]
    assert len(unmatched) == 2
    assert len({finding["id"] for finding in unmatched}) == 2


def mixed_pdf():
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    lines = [
        "PURCHASE ORDER",
        "Document number: PO-1",
        "Order reference: ORDER-1",
        "Currency: INR",
        "CBL-1 | Cable | 2 | m | 80 | 160",
        "Subtotal: 160",
        "Tax: 0",
        "Total: 160",
    ]
    for index, line in enumerate(lines):
        pdf.drawString(40, 750 - 22 * index, line)
    pdf.showPage()
    pdf.rect(40, 40, 300, 400)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def test_field_save_keeps_unreadable_page_warning(client, case):
    response = client.post(
        f"/api/cases/{case['id']}/documents",
        files={"files": ("mixed.pdf", mixed_pdf(), "application/pdf")},
    )
    assert response.status_code == 201
    doc_id = response.json()[0]["id"]
    process_all()
    before = client.get(f"/api/documents/{doc_id}").json()
    assert before["status"] == "needs_review"
    assert any("OCR" in warning for warning in before["data"]["warnings"])
    response = client.put(f"/api/documents/{doc_id}/correction", json=before["data"])
    assert response.status_code == 200
    after = client.get(f"/api/documents/{doc_id}").json()
    assert after["status"] == "needs_review"
    assert any("OCR" in warning for warning in after["data"]["warnings"])


def test_reprocessing_keeps_first_retained_extraction(client, case, monkeypatch):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    first = client.get(f"/api/documents/{doc_id}").json()["original"]
    extractor = worker.extract_pdf

    def changed_supplier(*args, **kwargs):
        extraction, pages = extractor(*args, **kwargs)
        extraction["supplier"] = "A different parser result (fictional)"
        return extraction, pages

    monkeypatch.setattr(worker, "extract_pdf", changed_supplier)
    assert client.post(f"/api/documents/{doc_id}/retry").status_code == 200
    process_all()
    after = client.get(f"/api/documents/{doc_id}").json()
    assert after["original"] == first
    assert after["latest_raw"]["supplier"] == "A different parser result (fictional)"
    assert len(after["processing_runs"]) == 2


def test_reprocess_status_uses_effective_review(client, case):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    data["line_items"][0]["quantity"] = None
    assert client.put(f"/api/documents/{doc_id}/correction", json=data).status_code == 200
    assert client.post(f"/api/documents/{doc_id}/retry").status_code == 200
    process_all()
    after = client.get(f"/api/documents/{doc_id}").json()
    assert after["data"]["line_items"][0]["quantity"] is None
    assert after["status"] == "needs_review"


def test_conflicting_skus_do_not_match_by_description():
    reference, target = document(), document("b", document_type="invoice")
    reference["data"]["line_items"][0]["sku"] = "CBL-A"
    target["data"]["line_items"][0].update(sku="CBL-B", quantity="120")
    kinds = {finding["kind"] for finding in verify_documents([reference, target])}
    assert "quantity_difference" not in kinds
    assert "identifier_conflict" in kinds


def test_exact_description_precedes_fuzzy_match():
    reference, target = document(), document("b", document_type="invoice")
    reference["data"]["line_items"][0].update(sku=None, description="Steel bolt M8")
    target["data"]["line_items"][0].update(sku=None, description="Steel bolt M8", quantity="120")
    similar = copy.deepcopy(target["data"]["line_items"][0])
    similar["description"] = "Steel bolt M10"
    target["data"]["line_items"].append(similar)
    kinds = {finding["kind"] for finding in verify_documents([reference, target])}
    assert "ambiguous_match" not in kinds
    assert "quantity_difference" in kinds


def test_stale_browser_review_receives_conflict(client, case):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    older = client.get(f"/api/documents/{doc_id}").json()["data"]
    newer = copy.deepcopy(older)
    newer["supplier"] = "Reviewed supplier (fictional)"
    assert client.put(f"/api/documents/{doc_id}/correction", json=newer).status_code == 200
    older["supplier"] = "Stale supplier (fictional)"
    assert client.put(f"/api/documents/{doc_id}/correction", json=older).status_code == 409
    assert client.get(f"/api/documents/{doc_id}").json()["data"]["supplier"] == newer["supplier"]


def test_stale_row_edit_conflicts_before_row_validation(client, case):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    older = client.get(f"/api/documents/{doc_id}").json()["data"]
    newer = copy.deepcopy(older)
    newer["line_items"] = []
    assert client.put(f"/api/documents/{doc_id}/correction", json=newer).status_code == 200
    assert client.put(f"/api/documents/{doc_id}/correction", json=older).status_code == 409
    assert client.get(f"/api/documents/{doc_id}").json()["data"]["line_items"] == []
