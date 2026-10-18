from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1] or " " in value:
            raise ValueError("Enter a valid email address")
        return value


class CaseInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    tolerance: Decimal = Field(default=Decimal("0.01"), ge=0, le=100)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("Case name cannot be blank")
        return value.strip()


class Source(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    snippet: str
    bbox: list[float] | None = None
    extraction_revision: int | None = None


class SourceLimitation(BaseModel):
    id: str
    kind: str
    message: str
    page: int | None = None


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, max_length=80)
    sku: str | None = Field(default=None, max_length=100)
    description: str = Field(max_length=500)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    unit_price: Decimal | None = Field(default=None, ge=0)
    amount: Decimal | None = Field(default=None, ge=0)
    source: Source | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal["purchase_order", "invoice", "quotation", "unknown"] = "unknown"
    document_number: str | None = Field(default=None, max_length=160)
    order_reference: str | None = Field(default=None, max_length=160)
    supplier: str | None = Field(default=None, max_length=300)
    customer: str | None = Field(default=None, max_length=300)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    date: str | None = Field(default=None, max_length=40)
    line_items: list[LineItem] = Field(default_factory=list, max_length=200)
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax: Decimal | None = Field(default=None, ge=0)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    total: Decimal | None = Field(default=None, ge=0)
    sources: dict[str, Source] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    source_warnings: list[SourceLimitation] = Field(default_factory=list)
    revision: int | None = Field(default=None, ge=0)
    extraction_revision: int | None = Field(default=None, ge=1)
    confidence_label: str = "Rule-based heuristic; not a calibrated probability"

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency_case(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("subtotal", "tax", "tax_rate", "total")
    @classmethod
    def finite_values(cls, value):
        if value is not None and not value.is_finite():
            raise ValueError("Values must be finite")
        return value


class LimitationResolution(BaseModel):
    revision: int = Field(ge=0)
    reason: str = Field(min_length=15, max_length=1000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 15:
            raise ValueError("Describe the manual source review in at least 15 nonblank characters")
        return value


class ComparisonInput(BaseModel):
    revision: int = Field(ge=0)
    reference_document_id: str | None = None
    target_document_ids: list[str] = Field(default_factory=list, max_length=100)


class SearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    mode: Literal["auto", "keyword"] = "auto"
    scope: Literal["original", "reviewed"] = "original"
