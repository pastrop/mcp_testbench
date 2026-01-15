from decimal import Decimal
from typing import Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """Represents a single transaction from the Excel file."""

    transaction_id: Optional[str] = None
    amount: Optional[Decimal] = None
    commission: Optional[Decimal] = None
    rolling_reserve: Optional[Decimal] = None
    chargeback_fee: Optional[Decimal] = None
    refund_fee: Optional[Decimal] = None
    date: Optional[datetime] = None
    status: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)  # Original row data

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat() if v else None
        }


class FeeBreakdown(BaseModel):
    """Breakdown of fee calculation."""

    amount: Decimal
    rate: Optional[Decimal] = None
    calculation: str


class FeeVerificationResult(BaseModel):
    """Result of comparing actual vs expected fee."""

    fee_type: str  # "remuneration", "chargeback", "refund", "rolling_reserve"
    expected: Decimal
    actual: Optional[Decimal]
    difference: Optional[Decimal] = None
    status: str  # "CORRECT", "OVERCHARGED", "UNDERCHARGED", "MISSING"
    within_tolerance: bool = False
    breakdown: Optional[FeeBreakdown] = None


class TransactionVerification(BaseModel):
    """Complete verification result for a single transaction."""

    transaction_id: Optional[str]
    verifications: Dict[str, FeeVerificationResult]
    overall_status: str  # "CORRECT", "HAS_ERRORS", "QUESTIONABLE"
    error_count: int = 0
    confidence: float = Field(ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    raw_transaction: Optional[Transaction] = None

    class Config:
        json_encoders = {
            Decimal: str
        }
