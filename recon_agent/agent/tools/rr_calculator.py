from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class RollingReserveTracker:
    """
    Track Rolling Reserve (RR) balance with:
    - 10% rate per transaction
    - €37,500 cap
    - 180-day holding period
    """

    def __init__(
        self,
        cap: Decimal = Decimal("37500.00"),
        holding_days: int = 180
    ):
        """
        Initialize RR tracker.

        Args:
            cap: Maximum RR balance (default: €37,500)
            holding_days: Days to hold RR before release (default: 180)
        """
        self.cap = cap
        self.holding_days = holding_days
        self.current_balance = Decimal("0.00")
        self.holdings: List[Dict] = []  # List of {date, amount}

    def calculate_rr(
        self,
        amount: Decimal,
        rate: Decimal = Decimal("0.1"),
        date: Optional[datetime] = None
    ) -> Dict:
        """
        Calculate RR for a transaction.

        Args:
            amount: Transaction amount
            rate: RR rate (default: 0.1 = 10%)
            date: Transaction date (for release tracking)

        Returns:
            Dictionary with:
            {
                "rr_amount": Decimal,          # Calculated RR (10% of amount)
                "applied_amount": Decimal,     # Actually reserved (may be less due to cap)
                "capped": bool,                # Was cap reached?
                "current_balance": Decimal,    # Current total RR balance
                "remaining_capacity": Decimal, # Space left before cap
                "breakdown": {
                    "amount": Decimal,
                    "rate": Decimal,
                    "calculation": str
                }
            }
        """
        # Calculate 10% RR
        rr_amount = (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # Check against cap
        if self.current_balance + rr_amount > self.cap:
            applied_amount = self.cap - self.current_balance
            capped = True
        else:
            applied_amount = rr_amount
            capped = False

        # Add to balance
        self.current_balance += applied_amount

        # Track holding (for 180-day release)
        if date:
            self.holdings.append({
                "date": date,
                "amount": applied_amount
            })

        # Calculate remaining capacity
        remaining_capacity = self.cap - self.current_balance

        return {
            "rr_amount": rr_amount,
            "applied_amount": applied_amount,
            "capped": capped,
            "current_balance": self.current_balance,
            "remaining_capacity": remaining_capacity,
            "breakdown": {
                "amount": amount,
                "rate": rate,
                "calculation": f"{amount} × {rate} = {rr_amount}" +
                              (f" (capped at {applied_amount})" if capped else "")
            }
        }

    def release_expired(self, current_date: datetime) -> Decimal:
        """
        Release RR held for more than holding_days.

        Args:
            current_date: Current date for comparison

        Returns:
            Total amount released
        """
        release_date = current_date - timedelta(days=self.holding_days)

        # Find holdings to release
        to_release = [h for h in self.holdings if h["date"] <= release_date]
        self.holdings = [h for h in self.holdings if h["date"] > release_date]

        # Calculate total released
        released_amount = sum(h["amount"] for h in to_release)
        self.current_balance -= released_amount

        return released_amount.quantize(Decimal("0.01"), ROUND_HALF_UP)

    def get_status(self) -> Dict:
        """
        Get current RR tracker status.

        Returns:
            Dictionary with current state
        """
        return {
            "current_balance": self.current_balance,
            "cap": self.cap,
            "utilization_pct": (
                (self.current_balance / self.cap * 100).quantize(Decimal("0.01"))
                if self.cap > 0 else Decimal("0.00")
            ),
            "remaining_capacity": self.cap - self.current_balance,
            "holding_count": len(self.holdings),
            "oldest_holding": (
                self.holdings[0]["date"] if self.holdings else None
            )
        }

    def reset(self):
        """Reset tracker to initial state."""
        self.current_balance = Decimal("0.00")
        self.holdings = []


def calculate_expected_rr(
    amount: Decimal,
    rate: Decimal = Decimal("0.1"),
    cap: Decimal = Decimal("37500.00")
) -> Dict:
    """
    Calculate expected RR for a single transaction (stateless).

    Args:
        amount: Transaction amount
        rate: RR rate (default: 0.1 = 10%)
        cap: Maximum RR per transaction (default: €37,500)

    Returns:
        Dictionary with RR calculation
    """
    rr_amount = (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    # Apply cap if RR exceeds maximum
    if rr_amount > cap:
        capped_amount = cap
        is_capped = True
    else:
        capped_amount = rr_amount
        is_capped = False

    return {
        "rr_amount": capped_amount,
        "breakdown": {
            "amount": amount,
            "rate": rate,
            "calculation": f"{amount} × {rate} = {rr_amount}" + (f" (capped at {capped_amount})" if is_capped else "")
        }
    }
