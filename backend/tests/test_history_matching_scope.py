import copy
import json

import httpx
import pytest
from app import worker
from app.services import retrieval
from app.services.verification import verify_documents

from .test_api_worker import process_all, upload
from .test_review_regressions import mixed_pdf
from .test_verification import document


def test_row_reordering_keeps_findings_and_review_status(client, case):
    documents = upload(client, case)
    process_all()
    doc_id = documents[0]["id"]
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    for _ in range(2):
        data["line_items"].append(
            {
                "id": None,
                "description": "Washer",
                "quantity": "2",
                "unit": "pcs",
                "unit_price": "1",
                "amount": "2",
                "source": None,
            }
        )
    data["subtotal"] = data["total"] = "8004"
    assert client.put(f"/api/documents/{doc_id}/correction", json=data).status_code == 200
    findings = client.get(f"/api/cases/{case['id']}/findings").json()
    unmatched = [finding for finding in findings if finding["kind"] == "missing_item"]
    assert len(unmatched) == 2
    marked = unmatched[0]["id"]
    assert (
        client.patch(
            f"/api/cases/{case['id']}/findings/{marked}", json={"review_status": "acknowledged"}
        ).status_code
        == 200
    )
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    identities = {item["id"] for item in data["line_items"]}
    data["line_items"].reverse()
    assert client.put(f"/api/documents/{doc_id}/correction", json=data).status_code == 200
    after = client.get(f"/api/cases/{case['id']}/findings").json()
    assert {finding["id"] for finding in after} == {finding["id"] for finding in findings}
    assert (
        next(finding for finding in after if finding["id"] == marked)["review_status"]
        == "acknowledged"
    )
    assert {
        item["id"] for item in client.get(f"/api/documents/{doc_id}").json()["data"]["line_items"]
    } == identities


def test_material_quantity_change_reopens_finding(client, case):
    documents = upload(client, case)
    process_all()
    findings = client.get(f"/api/cases/{case['id']}/findings").json()
    quantity = next(finding for finding in findings if finding["kind"] == "quantity_difference")
    client.patch(
        f"/api/cases/{case['id']}/findings/{quantity['id']}", json={"review_status": "resolved"}
    )
    doc_id = documents[1]["id"]
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    data["line_items"][0].update(quantity="130", amount="11050")
    data["subtotal"] = data["total"] = "11050"
    assert client.put(f"/api/documents/{doc_id}/correction", json=data).status_code == 200
    changed = next(
        finding
        for finding in client.get(f"/api/cases/{case['id']}/findings").json()
        if finding["kind"] == "quantity_difference"
    )
    assert changed["id"] != quantity["id"] and changed["review_status"] == "open"


def test_duplicate_supplied_identity_is_invalid_not_deduplicated(client, case):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    data["line_items"].append(copy.deepcopy(data["line_items"][0]))
    assert client.put(f"/api/documents/{doc_id}/correction", json=data).status_code == 422


def test_structural_warning_resolution_is_explicit_and_audited(client, case):
    response = client.post(
        f"/api/cases/{case['id']}/documents",
        files={"files": ("mixed.pdf", mixed_pdf(), "application/pdf")},
    )
    doc_id = response.json()[0]["id"]
    process_all()
    detail = client.get(f"/api/documents/{doc_id}").json()
    warning = detail["data"]["source_warnings"][0]
    assert warning["page"] == 2 and detail["status"] == "needs_review"
    response = client.post(
        f"/api/documents/{doc_id}/source-limitations/{warning['id']}/resolve",
        json={
            "revision": detail["revision"],
            "reason": "Manually inspected page 2: decorative blank page, no procurement fields.",
        },
    )
    assert response.status_code == 200
    after = client.get(f"/api/documents/{doc_id}").json()
    assert after["status"] == "completed" and not after["data"]["source_warnings"]
    assert after["corrections"][0]["action"] == "source_resolution"
    assert "page 2" in after["corrections"][0]["resolution"]["reason"]
    assert warning["id"] in {item["id"] for item in after["resolved_limitations"]}
    assert client.post(f"/api/documents/{doc_id}/retry").status_code == 200
    process_all()
    assert client.get(f"/api/documents/{doc_id}").json()["status"] == "completed"


def test_genuinely_corrected_field_warning_disappears(client, case):
    doc_id = upload(client, case, ("incomplete_invoice.pdf",))[0]["id"]
    process_all()
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    assert any("document number" in message for message in data["warnings"])
    data["document_number"] = "INV-reviewed"
    for item in data["line_items"]:
        item["quantity"] = "100"
    assert client.put(f"/api/documents/{doc_id}/correction", json=data).status_code == 200
    after = client.get(f"/api/documents/{doc_id}").json()
    assert not after["data"]["warnings"]
    assert after["status"] == "completed"


def test_correction_stays_bound_to_earlier_run(client, case, monkeypatch):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
    data["supplier"] = "Reviewed supplier"
    assert client.put(f"/api/documents/{doc_id}/correction", json=data).status_code == 200
    extractor = worker.extract_pdf

    def different_rows(*args):
        raw, pages = extractor(*args)
        raw["line_items"][0]["sku"] = "DIFFERENT-RAW-ID"
        raw["line_items"][0]["source"]["snippet"] = "Different parser source interpretation"
        return raw, pages

    monkeypatch.setattr(worker, "extract_pdf", different_rows)
    assert client.post(f"/api/documents/{doc_id}/retry").status_code == 200
    process_all()
    detail = client.get(f"/api/documents/{doc_id}").json()
    assert detail["data"]["supplier"] == "Reviewed supplier"
    assert detail["data"]["extraction_revision"] == 1
    assert detail["latest_raw"]["extraction_revision"] == 2
    assert detail["data"]["line_items"][0]["id"] != detail["latest_raw"]["line_items"][0]["id"]
    assert detail["data"]["line_items"][0]["source"]["extraction_revision"] == 1
    assert detail["corrections"][0]["extraction_revision"] == 1
    assert detail["processing_runs"][0]["metadata"]["parser_version"]


def test_unchanged_reprocess_keeps_row_and_finding_identity(client, case):
    documents = upload(client, case)
    process_all()
    before = client.get(f"/api/cases/{case['id']}/findings").json()
    mark = before[0]["id"]
    client.patch(f"/api/cases/{case['id']}/findings/{mark}", json={"review_status": "acknowledged"})
    client.post(f"/api/documents/{documents[0]['id']}/retry")
    process_all()
    after = client.get(f"/api/cases/{case['id']}/findings").json()
    assert {finding["id"] for finding in before} == {finding["id"] for finding in after}
    assert (
        next(finding for finding in after if finding["id"] == mark)["review_status"]
        == "acknowledged"
    )


def test_multiple_invoices_are_individual_targets_never_target_pairs():
    reference, first, second = document(), document("b"), document("c")
    results = verify_documents([reference, first, second])
    assert any(finding["kind"] == "multiple_invoices" for finding in results)
    assert not any(finding["document_ids"] == ["b", "c"] for finding in results)
    results = verify_documents([first, second])
    assert any(finding["kind"] == "comparison_not_ready" for finding in results)
    assert not any(finding["kind"].endswith("_difference") for finding in results)


def test_fuzzy_only_candidate_is_review_not_confirmed_difference():
    reference, target = document(), document("b")
    reference["data"]["line_items"][0].update(sku=None, description="Steel bolts M8")
    target["data"]["line_items"][0].update(sku=None, description="Steel bolt M8", quantity="120")
    results = verify_documents([reference, target])
    assert any(finding["kind"] == "fuzzy_match" for finding in results)
    assert not any(finding["kind"] == "quantity_difference" for finding in results)


def test_competing_source_rows_remain_ambiguous():
    reference, target = document(), document("b")
    reference["data"]["line_items"].append(copy.deepcopy(reference["data"]["line_items"][0]))
    results = verify_documents([reference, target])
    assert sum(finding["kind"] == "ambiguous_match" for finding in results) == 2
    assert len({finding["id"] for finding in results}) == len(results)


def test_explicit_comparison_and_case_readiness(client, case):
    documents = upload(client, case)
    process_all()
    current = client.get(f"/api/cases/{case['id']}").json()
    assert current["comparison"]["reference_document_id"] == documents[0]["id"]
    assert current["readiness"]["all_documents_checked"]
    response = client.put(
        f"/api/cases/{case['id']}/comparison",
        json={
            "revision": current["revision"],
            "reference_document_id": documents[1]["id"],
            "target_document_ids": [documents[0]["id"]],
        },
    )
    assert response.status_code == 200 and response.json()["comparison"]["mode"] == "explicit"
    assert all(
        finding["document_ids"][0] == documents[1]["id"]
        for finding in client.get(f"/api/cases/{case['id']}/findings").json()
    )
    assert (
        client.put(
            f"/api/cases/{case['id']}/comparison",
            json={"revision": current["revision"], "reference_document_id": documents[1]["id"]},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("scope", ["original", "reviewed"])
def test_provider_receives_complete_scoped_effective_values(client, case, monkeypatch, scope):
    documents = upload(client, case)
    process_all()
    invoice_id = documents[1]["id"]
    data = client.get(f"/api/documents/{invoice_id}").json()["data"]
    data["supplier"] = "Corrected fictional supplier"
    data["line_items"][0].update(quantity="100", unit_price="80", amount="8000")
    data["subtotal"] = data["total"] = "8000"
    assert client.put(f"/api/documents/{invoice_id}/correction", json=data).status_code == 200
    assert client.get(f"/api/cases/{case['id']}/findings").json() == []
    monkeypatch.setattr(retrieval.settings(), "anthropic_api_key", "synthetic-test-key")

    def fake_post(url, **kwargs):
        context = json.loads(kwargs["json"]["messages"][0]["content"])
        assert context["scope"] == scope
        if scope == "reviewed":
            assert context["deterministic_verification"] == []
            record = next(
                record
                for record in context["reviewed_records"]
                if record["document_id"] == invoice_id
            )
            assert record["values"]["supplier"] == "Corrected fictional supplier"
            assert record["values"]["line_items"][0]["quantity"] == "100"
            assert (
                record["provenance"]["correction_id"]
                and record["provenance"]["extraction_revision"] == 1
            )
            source_id = record["id"]
        else:
            assert {"quantity_difference", "unit_price_difference", "subtotal_difference"} <= {
                finding["kind"] for finding in context["deterministic_verification"]
            }
            assert context["reviewed_records"] == []
            assert "Corrected fictional supplier" not in json.dumps(
                context["untrusted_document_evidence"]
            )
            source_id = context["untrusted_document_evidence"][0]["id"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"answer": "Scoped synthetic answer.", "source_ids": [source_id]}
                        ),
                    }
                ]
            },
        )

    monkeypatch.setattr(retrieval.httpx, "post", fake_post)
    response = client.post(
        f"/api/cases/{case['id']}/search", json={"query": "Copper cable", "scope": scope}
    )
    assert response.status_code == 200
    assert response.json()["cited_source_ids"]
