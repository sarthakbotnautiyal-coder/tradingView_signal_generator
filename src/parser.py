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
    timestamp: Optional[datetime] = None  # When received in Telegram
    parsed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize to dict for JSON logging."""
        return {
            "raw_text": self.raw_text,
            "symbol": self.symbol,
            "price": self.price,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "parsed_at": self.parsed_at.isoformat(),
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

        return AlertMessage(
            raw_text=text.strip(),
            symbol=symbol,
            price=price,
            timestamp=datetime.now(timezone.utc),
        )

    def parse_or_raise(self, text: str) -> AlertMessage:
        """Parse or raise ValueError if invalid."""
        result = self.parse(text)
        if result is None:
            raise ValueError(f"Could not parse TradingView alert: {text!r}")
        return result