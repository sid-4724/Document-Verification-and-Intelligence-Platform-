from copy import deepcopy
from decimal import Decimal

import pytest
from app.schemas import Extraction, LineItem
from app.services.extraction import number
from app.services.verification import verify_documents


def document(id="a", **changes):
    data = {
        "document_type": "purchase_order" if id == "a" else "invoice",
        "document_number": "PO-1",
        "order_reference": "REF-1",
        "currency": "INR",
        "line_items": [
            {
                "sku": "A1",
                "description": "Copper cable",
                "quantity": "100",
                "unit": "m",
                "unit_price": "80",
                "amount": "8000",
            }
        ],
        "subtotal": "8000",
        "tax": "0",
        "total": "8000",
        "warnings": [],
        "sources": {},
    }
    data.update(changes)
    return {"id": id, "filename": f"{id}.pdf", "data": data}


def kinds(docs, tolerance=Decimal("0.01")):
    return {f["kind"] for f in verify_documents(docs, tolerance)}


def test_decimal_and_tolerance():
    doc = document(subtotal="0.30", total="0.30")
    doc["data"]["line_items"][0].update(quantity="3", unit_price="0.10", amount="0.30")
    assert "arithmetic_error" not in kinds([doc])
    doc["data"]["line_items"][0]["amount"] = "0.31"
    assert "arithmetic_error" not in kinds([doc])
    assert "arithmetic_error" in kinds([doc], Decimal("0.001"))


def test_missing_is_not_zero():
    assert number("0") == Decimal(0)
    assert number("?") is None
    assert number("NaN") is None
    assert Extraction().subtotal is None
    a, b = document(), document("b")
    b["data"]["line_items"][0]["quantity"] = None
    result = kinds([a, b])
    assert "quantity_difference" not in result
    assert "extraction_uncertainty" in result
    b["data"]["line_items"][0]["quantity"] = "0"
    assert "quantity_difference" in kinds([a, b])


def test_quantity_price_subtotal_example():
    a, b = document(), document("b", document_type="invoice", subtotal="10200", total="10200")
    b["data"]["line_items"][0].update(quantity="120", unit_price="85", amount="10200")
    results = verify_documents([a, b])
    assert {"quantity_difference", "unit_price_difference", "subtotal_difference"} <= {
        r["kind"] for r in results
    }
    assert any("2,200.00" in r["explanation"] for r in results)
    assert "arithmetic_error" not in {r["kind"] for r in results}


@pytest.mark.parametrize(
    "left,right", [("m", "metres"), ("pcs", "pieces"), ("kg", "kilograms"), ("hr", "hours")]
)
def test_unit_aliases(left, right):
    a, b = document(), document("b")
    a["data"]["line_items"][0]["unit"] = left
    b["data"]["line_items"][0].update(unit=right, quantity="120")
    assert "quantity_difference" in kinds([a, b])
    assert "unit_incompatible" not in kinds([a, b])


def test_incompatible_units_and_currency():
    a, b = document(), document("b", currency="USD", subtotal="10200")
    b["data"]["line_items"][0].update(unit="pcs", quantity="120", unit_price="85")
    result = kinds([a, b])
    assert {"currency_incompatible", "unit_incompatible"} <= result
    assert not {"quantity_difference", "unit_price_difference", "subtotal_difference"} & result


def test_ambiguous_matching_never_forces_or_reports_extra():
    a, b = document(), document("b")
    b["data"]["line_items"].append(deepcopy(b["data"]["line_items"][0]))
    result = kinds([a, b])
    assert "ambiguous_match" in result
    assert not {"quantity_difference", "extra_item"} & result


def test_missing_item_vs_unreadable_table():
    a, b = document(), document("b")
    a["data"]["line_items"].append(
        {
            "sku": "B2",
            "description": "Connector",
            "quantity": "2",
            "unit": "pcs",
            "unit_price": "1",
            "amount": "2",
        }
    )
    assert "missing_item" in kinds([a, b])
    b["data"]["warnings"] = ["Missing subtotal"]
    assert "missing_item" not in kinds([a, b])
    assert "possible_missing_item" in kinds([a, b])
    b["data"]["line_items"] = []
    assert "missing_item" not in kinds([a, b])


def test_reference_difference_skips_unrelated_item_comparison():
    a, b = document(), document("b", order_reference="OTHER")
    b["data"]["line_items"][0]["quantity"] = "120"
    assert "order_reference_difference" in kinds([a, b])
    assert "quantity_difference" not in kinds([a, b])


def test_tax_only_with_explicit_rate():
    doc = document(tax="120", total="8120")
    assert "arithmetic_error" not in kinds([doc])
    doc["data"]["tax_rate"] = "18"
    assert "arithmetic_error" in kinds([doc])


def test_negative_and_nonfinite_edits_rejected():
    for invalid in ("-1", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            LineItem(description="Cable", quantity=invalid)


@pytest.mark.parametrize("unknown", [None, "?", "unknown", "", " ", "N/A"])
def test_unknown_units_cannot_confirm_quantity_or_price_difference(unknown):
    reference, target = document(), document("b")
    reference["data"]["line_items"][0]["unit"] = unknown
    target["data"]["line_items"][0].update(unit=unknown, quantity="120", unit_price="85")
    result = kinds([reference, target])
    assert "unit_incompatible" in result
    assert not {"quantity_difference", "unit_price_difference"} & result
