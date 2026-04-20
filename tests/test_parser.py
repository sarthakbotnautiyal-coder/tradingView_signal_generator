"""Tests for the TradingView alert parser."""

import pytest
from datetime import datetime, timezone

from src.parser import AlertParser, AlertMessage


class TestAlertParser:
    """Tests for AlertParser."""

    def setup_method(self):
        """Set up fresh parser for each test."""
        self.parser = AlertParser()

    def test_parse_standard_alert(self):
        """Parse standard TradingView alert format."""
        text = "TradingView Alert for SPX, Price = 7095.15"
        alert = self.parser.parse(text)

        assert alert is not None
        assert alert.symbol == "SPX"
        assert alert.price == 7095.15
        assert alert.raw_text == text

    def test_parse_lowercase_alert(self):
        """Parser should be case-insensitive."""
        text = "tradingview alert for spx, price = 5000.00"
        alert = self.parser.parse(text)

        assert alert is not None
        assert alert.symbol == "SPX"
        assert alert.price == 5000.0

    def test_parse_qqq_alert(self):
        """Parse QQQ symbol."""
        text = "TradingView Alert for QQQ, Price = 450.20"
        alert = self.parser.parse(text)

        assert alert is not None
        assert alert.symbol == "QQQ"
        assert alert.price == 450.20

    def test_parse_tsla_alert(self):
        """Parse TSLA symbol with lowercase."""
        text = "TradingView Alert for tsla, Price = 250.75"
        alert = self.parser.parse(text)

        assert alert is not None
        assert alert.symbol == "TSLA"
        assert alert.price == 250.75

    def test_parse_with_extra_spaces(self):
        """Handle extra whitespace."""
        text = "  TradingView Alert for   SPX  ,  Price   =   7095.15  "
        alert = self.parser.parse(text)

        assert alert is not None
        assert alert.symbol == "SPX"
        assert alert.price == 7095.15

    def test_parse_empty_string(self):
        """Return None for empty string."""
        assert self.parser.parse("") is None
        assert self.parser.parse("   ") is None

    def test_parse_invalid_format(self):
        """Return None for unrecognised format."""
        assert self.parser.parse("Hello world") is None
        assert self.parser.parse("TradingView Alert") is None
        assert self.parser.parse("SPX trading at 7095") is None

    def test_parse_missing_symbol(self):
        """Return None when symbol part is missing."""
        assert self.parser.parse("TradingView Alert for , Price = 100") is None

    def test_parse_missing_price(self):
        """Return None when price part is missing."""
        assert self.parser.parse("TradingView Alert for SPX, Price = ") is None

    def test_parse_non_numeric_price(self):
        """Return None for non-numeric price."""
        text = "TradingView Alert for SPX, Price = abc"
        assert self.parser.parse(text) is None

    def test_parse_integer_price(self):
        """Handle integer price without decimal."""
        text = "TradingView Alert for SPX, Price = 7095"
        alert = self.parser.parse(text)

        assert alert is not None
        assert alert.price == 7095.0

    def test_parse_timestamp_set(self):
        """Parsed alert should have timestamp set."""
        text = "TradingView Alert for SPX, Price = 7095.15"
        alert = self.parser.parse(text)

        assert alert is not None
        assert alert.timestamp is not None
        assert alert.parsed_at is not None

    def test_parse_or_raise_success(self):
        """parse_or_raise returns alert on success."""
        text = "TradingView Alert for SPX, Price = 7095.15"
        alert = self.parser.parse_or_raise(text)

        assert alert.symbol == "SPX"
        assert alert.price == 7095.15

    def test_parse_or_raise_failure(self):
        """parse_or_raise raises ValueError on failure."""
        with pytest.raises(ValueError, match="Could not parse"):
            self.parser.parse_or_raise("invalid message")


class TestAlertMessage:
    """Tests for AlertMessage dataclass."""

    def test_to_dict(self):
        """Serialize to dict correctly."""
        alert = AlertMessage(
            raw_text="TradingView Alert for SPX, Price = 7095.15",
            symbol="SPX",
            price=7095.15,
            timestamp=datetime(2026, 4, 20, 15, 30, 0, tzinfo=timezone.utc),
        )

        d = alert.to_dict()

        assert d["raw_text"] == "TradingView Alert for SPX, Price = 7095.15"
        assert d["symbol"] == "SPX"
        assert d["price"] == 7095.15
        assert "2026-04-20T15:30:00" in d["timestamp"]

    def test_to_dict_with_no_timestamp(self):
        """Handle None timestamp in serialization."""
        alert = AlertMessage(
            raw_text="test",
            symbol=None,
            price=None,
            timestamp=None,
        )

        d = alert.to_dict()

        assert d["timestamp"] is None