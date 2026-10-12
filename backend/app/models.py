"""Pydantic schemas for receipt extraction.

`Receipt` is the schema the LLM must fill in. `ExtractedReceipt` wraps it with
file metadata and review status produced by our own code.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    description: str
    amount: float | None = None


class FieldConfidence(BaseModel):
    vendor: float = Field(ge=0, le=1, description="0-1 confidence the vendor name is correct")
    date: float = Field(ge=0, le=1, description="0-1 confidence the date is correct (0 if absent)")
    total: float = Field(ge=0, le=1, description="0-1 confidence the total is correct")


class Receipt(BaseModel):
    readable: bool = Field(description="False if the image is not a receipt or is unreadable")
    vendor: str | None = Field(None, description="Merchant name as printed")
    receipt_date: dt.date | None = Field(
        None,
        description="Date on the receipt as ISO YYYY-MM-DD. Printed dates are day-first "
        "(DD/MM/YYYY). Null if no date is visible; never guess.",
    )
    total: float | None = Field(None, description="Final amount paid, including tax")
    tax: float | None = Field(None, description="Total tax amount, null if not shown")
    currency: str = Field(description="ISO 4217 code, e.g. INR, USD, SGD. Rs means INR.")
    category: str = Field(
        description="Short free-text description of the kind of expense, e.g. 'restaurant meal', "
        "'taxi ride', 'hotel stay', 'petrol'. This is only a hint; policy categories are assigned later."
    )
    nights: int | None = Field(None, description="Number of nights for a hotel stay, otherwise null")
    line_items: list[LineItem] = Field(default_factory=list)
    receipt_number: str | None = Field(None, description="Bill / invoice number if printed")
    payment_method: str | None = Field(None, description="e.g. CARD, CASH, UPI, if shown")
    confidence: FieldConfidence
    notes: str | None = Field(None, description="Anything unusual worth a human's attention")

    @field_validator("currency")
    @classmethod
    def _currency_code(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v


class ExtractedReceipt(BaseModel):
    source_file: str
    file_sha256: str
    model: str
    receipt: Receipt | None = None
    total_inr: float | None = None
    needs_review: bool = True
    review_reasons: list[str] = Field(default_factory=list)
    error: str | None = None
