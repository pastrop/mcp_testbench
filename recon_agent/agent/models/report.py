from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field
from .transaction import TransactionVerification


class ReportSummary(BaseModel):
    """Summary statistics for the verification report."""

    total_transactions: int
    correct_count: int
    erroneous_count: int
    questionable_count: int
    total_discrepancy: Decimal
    confidence_threshold: float = 0.5  # Below this = questionable

    @property
    def accuracy_rate(self) -> float:
        """Calculate accuracy rate as percentage."""
        if self.total_transactions == 0:
            return 0.0
        return round((self.correct_count / self.total_transactions) * 100, 2)

    class Config:
        json_encoders = {
            Decimal: str
        }


class ErrorDetail(BaseModel):
    """Details of an erroneous transaction."""

    transaction_id: Optional[str]
    fee_type: str
    expected: Decimal
    actual: Optional[Decimal]
    difference: Decimal
    difference_pct: Optional[Decimal] = None

    class Config:
        json_encoders = {
            Decimal: str
        }


class QuestionableDetail(BaseModel):
    """Details of a questionable transaction."""

    transaction_id: Optional[str]
    reason: str
    confidence: float
    assumptions: List[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    """Complete verification report structure."""

    summary: ReportSummary
    erroneous_transactions: List[ErrorDetail] = Field(default_factory=list)
    questionable_transactions: List[QuestionableDetail] = Field(default_factory=list)
    all_verifications: List[TransactionVerification] = Field(default_factory=list)
    contract_file: str
    excel_file: str
    sheet_name: Optional[str] = None
    timestamp: str

    class Config:
        json_encoders = {
            Decimal: str
        }
