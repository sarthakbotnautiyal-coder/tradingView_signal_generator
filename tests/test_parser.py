"""Tests for the TradingView + LuxAlgo alert parser."""

import pytest
from datetime import datetime, timezone

from src.parser import AlertParser, AlertMessage


class TestAlertParserTradingView:
    """Tests for standard TradingView alert format."""

    def setup_method(self):
        self.parser = AlertParser()

    def test_parse_standard_alert(self):
        text = "TradingView Alert for SPX, Price = 7095.15"
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.symbol == "SPX"
        assert alert.price == 7095.15
        assert alert.alert_type == "tradingview"
        assert alert.raw_text == text

    def test_parse_qqq_alert(self):
        text = "TradingView Alert for QQQ, Price = 450.20"
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.symbol == "QQQ"
        assert alert.price == 450.20

    def test_parse_lowercase(self):
        text = "tradingview alert for spx, price = 5000.00"
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.symbol == "SPX"
        assert alert.price == 5000.0

    def test_parse_extra_spaces(self):
        text = "  TradingView Alert for   SPX  ,  Price   =   7095.15  "
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.symbol == "SPX"
        assert alert.price == 7095.15

    def test_parse_integer_price(self):
        text = "TradingView Alert for SPX, Price = 7095"
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.price == 7095.0

    def test_parse_received_at_set(self):
        text = "TradingView Alert for SPX, Price = 7095.15"
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.received_at is not None
        assert alert.parsed_at is not None

    # ── Failures ──────────────────────────────────────────────

    def test_parse_empty_string(self):
        assert self.parser.parse("") is None
        assert self.parser.parse("   ") is None

    def test_parse_invalid_format(self):
        assert self.parser.parse("Hello world") is None
        assert self.parser.parse("TradingView Alert") is None
        assert self.parser.parse("SPX trading at 7095") is None

    def test_parse_missing_price(self):
        assert self.parser.parse("TradingView Alert for SPX, Price = ") is None

    def test_parse_non_numeric_price(self):
        assert self.parser.parse("TradingView Alert for SPX, Price = abc") is None

    def test_parse_or_raise_success(self):
        text = "TradingView Alert for SPX, Price = 7095.15"
        alert = self.parser.parse_or_raise(text)
        assert alert.symbol == "SPX"
        assert alert.price == 7095.15

    def test_parse_or_raise_failure(self):
        with pytest.raises(ValueError, match="Could not parse"):
            self.parser.parse_or_raise("invalid message")


class TestAlertParserRSIMACDBB:
    """Tests for LuxAlgo RSI/MACD/BB alert format."""

    def setup_method(self):
        self.parser = AlertParser()

    def test_parse_full_rsi_macd_bb(self):
        text = (
            "LuxAlgo RSI: 65.2 | MACD: 0.45 | Signal: 0.38 | Hist: 0.07 | "
            "BB Upper: 7030.00 | BB Middle: 7050.00 | BB Lower: 7070.00"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.alert_type == "rsi_macd_bb"
        assert alert.rsi == 65.2
        assert alert.macd == 0.45
        assert alert.macd_signal == 0.38
        assert alert.macd_hist == 0.07
        assert alert.bb_upper == 7030.00
        assert alert.bb_middle == 7050.00
        assert alert.bb_lower == 7070.00
        # Symbol not in raw text → None
        assert alert.symbol is None

    def test_parse_rsi_macd_bb_with_spx_ticker(self):
        text = (
            "LuxAlgo RSI: 65.2 | MACD: 0.45 | Signal: 0.38 | Hist: 0.07 | "
            "BB Upper: 7030.00 | BB Middle: 7050.00 | BB Lower: 7070.00 | SPX"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.symbol == "SPX"

    def test_parse_rsi_macd_bb_leading_spaces(self):
        text = (
            "  LuxAlgo RSI: 50.0 | MACD: 0.0 | Signal: 0.0 | Hist: 0.0 | "
            "BB Upper: 7100 | BB Middle: 7120 | BB Lower: 7140"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.alert_type == "rsi_macd_bb"
        assert alert.rsi == 50.0

    def test_parse_rsi_macd_bb_negative_values(self):
        text = (
            "LuxAlgo RSI: 35.5 | MACD: -0.25 | Signal: -0.20 | Hist: -0.05 | "
            "BB Upper: 6900.50 | BB Middle: 6950.00 | BB Lower: 7000.50"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.macd == -0.25
        assert alert.macd_signal == -0.20
        assert alert.macd_hist == -0.05
        assert alert.bb_lower == 7000.50

    def test_parse_rsi_macd_bb_missing_bb_lower(self):
        """BB Lower missing — pattern requires all fields, so returns None."""
        text = (
            "LuxAlgo RSI: 65.2 | MACD: 0.45 | Signal: 0.38 | Hist: 0.07 | "
            "BB Upper: 7030.00 | BB Middle: 7050.00"
        )
        assert self.parser.parse(text) is None

    def test_parse_rsi_macd_bb_missing_rsi(self):
        """RSI field missing — pattern requires it, so returns None."""
        text = (
            "LuxAlgo RSI: 65.2 | MACD: 0.45 | Signal: 0.38 | Hist: 0.07 | "
            "BB Upper: 7030.00 | BB Middle: 7050.00 | BB Lower: 7070.00"
        )
        broken = text.replace("RSI: 65.2 | ", "")
        assert self.parser.parse(broken) is None


class TestAlertParserExit:
    """Tests for LuxAlgo Exit alert format."""

    def setup_method(self):
        self.parser = AlertParser()

    def test_parse_exit_long(self):
        text = (
            "LuxAlgo Exit Long @ 7095.15 | Entry: 7070.00 | "
            "P&L: +25.15 (+0.36%) | Reason: Trailing Stop"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.alert_type == "exit"
        assert alert.direction == "Long"
        assert alert.price == 7095.15
        assert alert.entry_price == 7070.00
        assert alert.pnl_points == 25.15
        assert alert.pnl_pct == 0.36
        assert alert.exit_reason == "Trailing Stop"

    def test_parse_exit_short_profit(self):
        text = (
            "LuxAlgo Exit Short @ 7050.00 | Entry: 7070.00 | "
            "P&L: +30.50 (+0.43%) | Reason: Target Hit"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.alert_type == "exit"
        assert alert.direction == "Short"
        assert alert.price == 7050.00
        assert alert.entry_price == 7070.00
        assert alert.pnl_points == 30.50
        assert alert.pnl_pct == 0.43

    def test_parse_exit_negative_pnl(self):
        """Negative P&L: sign on points AND sign inside parentheses."""
        text = (
            "LuxAlgo Exit Long @ 7050.00 | Entry: 7070.00 | "
            "P&L: -20.00 (-0.28%) | Reason: Stop Loss"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.direction == "Long"
        assert alert.pnl_points == -20.00
        assert alert.pnl_pct == -0.28

    def test_parse_exit_extra_whitespace(self):
        text = (
            "  LuxAlgo Exit  Long  @  7095.15  |  Entry:  7070.00  |  "
            "P&L:  +25.15  (+0.36%)  |  Reason:  Trailing Stop  "
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.alert_type == "exit"
        assert alert.direction == "Long"
        assert alert.pnl_points == 25.15

    def test_parse_exit_missing_entry(self):
        text = "LuxAlgo Exit Long @ 7095.15 | P&L: +25.15 (+0.36%) | Reason: Stop"
        assert self.parser.parse(text) is None


class TestAlertParserConfirmationPlus:
    """Tests for LuxAlgo Confirmation+ alert format."""

    def setup_method(self):
        self.parser = AlertParser()

    def test_parse_confirmation_plus_long(self):
        text = (
            "LuxAlgo Confirmation+ Long | Price: 7095.15 | "
            "RSI: 65 | MACD: 0.45 | Signal: 0.38"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.alert_type == "confirmation_plus"
        assert alert.signal == "Long"
        assert alert.price == 7095.15
        assert alert.rsi == 65.0
        assert alert.macd == 0.45
        assert alert.macd_signal == 0.38

    def test_parse_confirmation_plus_short(self):
        text = (
            "LuxAlgo Confirmation+ Short | Price: 7050.00 | "
            "RSI: 40 | MACD: -0.30 | Signal: -0.25"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.signal == "Short"
        assert alert.rsi == 40.0
        assert alert.macd == -0.30
        assert alert.macd_signal == -0.25

    def test_parse_confirmation_plus_neutral(self):
        text = (
            "LuxAlgo Confirmation+ Neutral | Price: 7070.00 | "
            "RSI: 50 | MACD: 0.0 | Signal: 0.0"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.signal == "Neutral"
        assert alert.rsi == 50.0

    def test_parse_confirmation_plus_extra_whitespace(self):
        text = (
            "  LuxAlgo Confirmation+  Long  |  Price:  7095.15  |  "
            "RSI:  65  |  MACD:  0.45  |  Signal:  0.38  "
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.signal == "Long"
        assert alert.price == 7095.15

    def test_parse_confirmation_plus_with_spx_ticker(self):
        """Ticker symbol embedded before Price: should be extracted."""
        text = (
            "LuxAlgo Confirmation+ Long | SPX | Price: 7095.15 | "
            "RSI: 65 | MACD: 0.45 | Signal: 0.38"
        )
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.symbol == "SPX"

    def test_parse_confirmation_plus_missing_signal(self):
        text = "LuxAlgo Confirmation+ | Price: 7095.15 | RSI: 65 | MACD: 0.45 | Signal: 0.38"
        assert self.parser.parse(text) is None


class TestAlertMessageToDict:
    """Tests for AlertMessage.to_dict()."""

    def test_to_dict_tradingview(self):
        alert = AlertMessage(
            raw_text="TradingView Alert for SPX, Price = 7095.15",
            symbol="SPX",
            price=7095.15,
            received_at="2026-04-20T15:30:00+00:00",
            parsed_at="2026-04-20T15:30:01+00:00",
            alert_type="tradingview",
        )
        d = alert.to_dict()
        assert d["symbol"] == "SPX"
        assert d["price"] == 7095.15
        assert d["ts"] == "2026-04-20T15:30:00+00:00"
        assert d["alert_type"] == "tradingview"
        assert "rsi" not in d

    def test_to_dict_rsi_macd_bb(self):
        alert = AlertMessage(
            raw_text="LuxAlgo RSI: 65.2 | MACD: 0.45 | Signal: 0.38 | Hist: 0.07 | "
                     "BB Upper: 7030.00 | BB Middle: 7050.00 | BB Lower: 7070.00",
            symbol="SPX",
            received_at="2026-04-20T15:30:00+00:00",
            parsed_at="2026-04-20T15:30:01+00:00",
            alert_type="rsi_macd_bb",
            rsi=65.2,
            macd=0.45,
            macd_signal=0.38,
            macd_hist=0.07,
            bb_upper=7030.00,
            bb_middle=7050.00,
            bb_lower=7070.00,
        )
        d = alert.to_dict()
        assert d["alert_type"] == "rsi_macd_bb"
        assert d["rsi"] == 65.2
        assert d["macd"] == 0.45
        assert d["bb_upper"] == 7030.00
        # price is None → still included (None serialization is intentional)
        assert "price" in d
        assert d["price"] is None
        assert "direction" not in d

    def test_to_dict_exit(self):
        alert = AlertMessage(
            raw_text="LuxAlgo Exit Long @ 7095.15 | Entry: 7070.00 | "
                     "P&L: +25.15 (+0.36%) | Reason: Trailing Stop",
            symbol="SPX",
            price=7095.15,
            received_at="2026-04-20T15:30:00+00:00",
            parsed_at="2026-04-20T15:30:01+00:00",
            alert_type="exit",
            direction="Long",
            entry_price=7070.00,
            pnl_points=25.15,
            pnl_pct=0.36,
            exit_reason="Trailing Stop",
        )
        d = alert.to_dict()
        assert d["alert_type"] == "exit"
        assert d["direction"] == "Long"
        assert d["pnl_points"] == 25.15
        assert d["exit_reason"] == "Trailing Stop"

    def test_to_dict_confirmation_plus(self):
        alert = AlertMessage(
            raw_text="LuxAlgo Confirmation+ Long | Price: 7095.15 | RSI: 65 | MACD: 0.45 | Signal: 0.38",
            symbol="SPX",
            price=7095.15,
            received_at="2026-04-20T15:30:00+00:00",
            parsed_at="2026-04-20T15:30:01+00:00",
            alert_type="confirmation_plus",
            signal="Long",
            rsi=65.0,
            macd=0.45,
            macd_signal=0.38,
        )
        d = alert.to_dict()
        assert d["alert_type"] == "confirmation_plus"
        assert d["signal"] == "Long"
        assert d["rsi"] == 65.0

    def test_to_dict_null_fields_present(self):
        """None fields should be present (explicit None serialization)."""
        alert = AlertMessage(
            raw_text="partial message",
            symbol=None,
            price=None,
            received_at=None,
            parsed_at="2026-04-20T15:30:01+00:00",
            alert_type="rsi_macd_bb",
            rsi=None,
            macd=None,
        )
        d = alert.to_dict()
        assert d["raw"] == "partial message"
        assert d["symbol"] is None
        assert d["price"] is None
        assert d["ts"] is None


class TestAlertParserPriority:
    """Parser should try TradingView format first (highest specificity)."""

    def setup_method(self):
        self.parser = AlertParser()

    def test_standard_before_luxalgo(self):
        """Standard format should win even if text could match LuxAlgo patterns."""
        text = "TradingView Alert for SPX, Price = 7095.15"
        alert = self.parser.parse(text)
        assert alert is not None
        assert alert.alert_type == "tradingview"
        assert alert.symbol == "SPX"
        assert alert.price == 7095.15
