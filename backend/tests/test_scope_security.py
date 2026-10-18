from app.main import app
from fastapi.testclient import TestClient

from .conftest import register
from .test_api_worker import process_all, upload


def test_reviewed_records_stay_in_selected_case(client, case):
    selected = upload(client, case)
    other = client.post("/api/cases", json={"name": "Other case"}).json()
    foreign = upload(client, other, ("sample_quotation.pdf",))[0]
    process_all()
    response = client.post(
        f"/api/cases/{case['id']}/search", json={"query": "Copper cable", "scope": "reviewed"}
    )
    assert response.status_code == 200
    records = response.json()["reviewed_records"]
    assert {record["document_id"] for record in records} == {
        document["id"] for document in selected
    }
    assert all(record["document_id"] != foreign["id"] for record in records)
    assert response.json()["answer"] is None


def test_new_review_and_comparison_endpoints_enforce_owner(client, case):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    with TestClient(app) as intruder:
        register(intruder, "scope-intruder@example.test")
        assert (
            intruder.post(
                f"/api/cases/{case['id']}/search",
                json={"query": "Copper cable", "scope": "reviewed"},
            ).status_code
            == 404
        )
        assert (
            intruder.put(
                f"/api/cases/{case['id']}/comparison",
                json={"revision": 0, "reference_document_id": doc_id},
            ).status_code
            == 404
        )
        assert (
            intruder.post(
                f"/api/documents/{doc_id}/source-limitations/unknown/resolve",
                json={"revision": 1, "reason": "This must not be accepted for another user's file"},
            ).status_code
            == 404
        )
