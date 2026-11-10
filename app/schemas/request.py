"""
Pydantic models for incoming API requests.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import validate_flipkart_url, validate_pincode


class ProductCheckRequest(BaseModel):
    productUrl: str = Field(..., description="Full Flipkart product URL")
    pincode: str = Field(..., description="6-digit Indian PIN code")

    @field_validator("productUrl")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_flipkart_url(v)

    @field_validator("pincode")
    @classmethod
    def _validate_pin(cls, v: str) -> str:
        return validate_pincode(v)


class BatchProductItem(BaseModel):
    productUrl: str = Field(..., description="Full Flipkart product URL")

    @field_validator("productUrl")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_flipkart_url(v)


class BatchCheckRequest(BaseModel):
    pincode: str = Field(..., description="6-digit Indian PIN code")
    products: list[BatchProductItem] = Field(
        ..., min_length=1, max_length=20, description="List of products to check"
    )

    @field_validator("pincode")
    @classmethod
    def _validate_pin(cls, v: str) -> str:
        return validate_pincode(v)
