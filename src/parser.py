"""Alert message parser for TradingView webhook format.

TradingView alert format:
    TradingView Alert for SPX, Price = 7095.15
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AlertMessage:
    """Parsed TradingView alert message."""

    raw_text: str
    symbol: Optional[str] = None
    price: Optional[float] = None
    received_at: Optional[str] = None  # UTC ISO8601
    parsed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """Serialize to alerts.log JSON format.

        Format: {"ts": "...", "symbol": "...", "price": ..., "raw": "..."}
        """
        return {
            "ts": self.received_at,
            "symbol": self.symbol,
            "price": self.price,
            "raw": self.raw_text,
        }


class AlertParser:
    """Parser for TradingView alert messages.

    Handles formats like:
        TradingView Alert for SPX, Price = 7095.15
        TradingView Alert for QQQ, Price = 450.20
        TradingView Alert for TSLA, Price = 250.75
    """

    # Pattern: "TradingView Alert for SYMBOL, Price = PRICE"
    PATTERN = re.compile(
        r"""
        ^\s*TradingView\s+Alert\s+for\s+
        (?P<symbol>[A-Za-z0-9_]+)\s*,\s*
        Price\s*=\s*
        (?P<price>[\d.]+)
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[AlertMessage]:
        """Parse raw text into AlertMessage.

        Args:
            text: Raw TradingView alert message.

        Returns:
            AlertMessage if parse succeeded, None otherwise.
        """
        if not text or not text.strip():
            return None

        match = self.PATTERN.search(text.strip())
        if not match:
            return None

        symbol = match.group("symbol").upper()
        try:
            price = float(match.group("price"))
        except (ValueError, TypeError):
            return None

        now_utc = datetime.now(timezone.utc).isoformat()
        return AlertMessage(
            raw_text=text.strip(),
            symbol=symbol,
            price=price,
            received_at=now_utc,
        )

    def parse_or_raise(self, text: str) -> AlertMessage:
        """Parse or raise ValueError if invalid."""
        result = self.parse(text)
        if result is None:
            raise ValueError(f"Could not parse TradingView alert: {text!r}")
        return result
