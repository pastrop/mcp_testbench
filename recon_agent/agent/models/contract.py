from decimal import Decimal
from typing import List
from pydantic import BaseModel, field_validator


class DintaresContract(BaseModel):
    """DINTARES contract fee structure with Decimal precision."""

    remuneration_rate: Decimal  # 0.038 (3.8%)
    chargeback_cost: Decimal    # 50.00 EUR
    refund_cost: Decimal        # 5.00 EUR
    rolling_reserve_rate: Decimal  # 0.1 (10%)
    rolling_reserve_days: int      # 180 days
    rolling_reserve_cap: Decimal   # 37,500.00 EUR
    chargeback_limit: Decimal      # 0.005 (0.5%)
    minimum_payment: Decimal       # 1.00 EUR
    monthly_card_limit: Decimal    # 5,000.00 EUR
    supported_cards: List[str]     # ["MasterCard", "Maestro"]
    currencies: List[str]          # ["EUR", "GBP", "USD", "AUD", "NOK"]

    @field_validator('*', mode='before')
    @classmethod
    def convert_to_decimal(cls, v, info):
        """Convert numeric values to Decimal for precision."""
        field_name = info.field_name

        # Skip non-numeric fields
        if field_name in ['supported_cards', 'currencies', 'rolling_reserve_days']:
            return v

        if isinstance(v, (int, float)):
            return Decimal(str(v))
        elif isinstance(v, str):
            try:
                return Decimal(v)
            except:
                return v
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "remuneration_rate": "0.038",
                "chargeback_cost": "50.00",
                "refund_cost": "5.00",
                "rolling_reserve_rate": "0.1",
                "rolling_reserve_days": 180,
                "rolling_reserve_cap": "37500.00",
                "chargeback_limit": "0.005",
                "minimum_payment": "1.00",
                "monthly_card_limit": "5000.00",
                "supported_cards": ["MasterCard", "Maestro"],
                "currencies": ["EUR", "GBP", "USD", "AUD", "NOK"]
            }
        }
