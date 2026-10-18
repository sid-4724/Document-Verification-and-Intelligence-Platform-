from .test_api_worker import process_all, upload


def test_save_acknowledges_assigned_row_ids_before_next_edit(client, case):
    doc_id = upload(client, case, ("matching_po.pdf",))[0]["id"]
    process_all()
    data = client.get(f"/api/documents/{doc_id}").json()["data"]
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
    data["subtotal"] = data["total"] = "8002"
    response = client.put(f"/api/documents/{doc_id}/correction", json=data)
    assert response.status_code == 200
    acknowledgement = response.json()
    assert acknowledgement["data"]["revision"] == acknowledgement["document_revision"]
    row_id = acknowledgement["data"]["line_items"][-1]["id"]
    assert row_id
    updated = acknowledgement["data"]
    updated["line_items"][-1].update(quantity="3", amount="3")
    updated["subtotal"] = updated["total"] = "8003"
    response = client.put(f"/api/documents/{doc_id}/correction", json=updated)
    assert response.status_code == 200
    assert response.json()["data"]["line_items"][-1]["id"] == row_id
