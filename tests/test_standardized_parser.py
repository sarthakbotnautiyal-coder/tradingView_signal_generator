"""Unit tests for src.db.standardized_parser."""

import pytest
from src.db.standardized_parser import (
    parse_fundamentals,
    parse_pattern_signal,
    parse_raw_record,
    _ALERT_TYPE_MAP,
)


class TestParseFundamentals:
    """Tests for parse_fundamentals()."""

    def test_parses_all_indicator_fields(self) -> None:
        raw = (
            "Fundamentals|Close:7160.44 |RSI:67.46 |MACD:8.2931 "
            "|Signal:8.8652 |Hist:-0.5721 |ADX:36.96 "
            "|VWAP:7135.39 |BB:7169.33-7151.42-7133.51"
        )
        result = parse_fundamentals(raw)

        assert result["alert_category"] == "indicator_snapshot"
        assert result["alert_type"] == "fundamentals"
        assert result["symbol"] == "SPX"
        assert result["price"] == 7160.44
        assert result["rsi"] == 67.46
        assert result["macd"] == 8.2931
        assert result["macd_signal"] == 8.8652
        assert result["macd_hist"] == -0.5721
        assert result["adx"] == 36.96
        assert result["vwap"] == 7135.39
        assert result["bb_upper"] == 7169.33
        assert result["bb_middle"] == 7151.42
        assert result["bb_lower"] == 7133.51

    def test_handles_no_bb(self) -> None:
        raw = "Fundamentals|Close:7160.44 |RSI:50 |MACD:0 |Signal:0 |Hist:0 |ADX:10 |VWAP:7160"
        result = parse_fundamentals(raw)

        assert result["bb_upper"] is None
        assert result["bb_middle"] is None
        assert result["bb_lower"] is None

    def test_handles_negative_macd_hist(self) -> None:
        raw = (
            "Fundamentals|Close:7100 |RSI:40 |MACD:-2.5 "
            "|Signal:-1.0 |Hist:-1.5 |ADX:20 |VWAP:7095 |BB:7110-7095-7080"
        )
        result = parse_fundamentals(raw)

        assert result["macd"] == -2.5
        assert result["macd_hist"] == -1.5
        assert result["bb_upper"] == 7110.0


class TestParsePatternSignal:
    """Tests for parse_pattern_signal()."""

    def test_bearish_reversal(self) -> None:
        raw = "Bearish reversal +|Close:7163.18"
        result = parse_pattern_signal(raw, "bearish")

        assert result["alert_category"] == "pattern_signal"
        assert result["alert_type"] == "bearish_reversal"
        assert result["symbol"] == "SPX"
        assert result["price"] == 7163.18
        assert result["pattern_description"] == "Bearish reversal +"
        assert result["signal_direction"] == "bearish"

    def test_overbought_hyperwave(self) -> None:
        raw = "Overbought Hyper Wave oscillator downward signal|Close:7156.03"
        result = parse_pattern_signal(raw, "overbought")

        assert result["alert_category"] == "pattern_signal"
        assert result["alert_type"] == "overbought_hyperwave"
        assert result["price"] == 7156.03
        assert result["pattern_description"] == "Overbought Hyper Wave oscillator downward signal"
        assert result["signal_direction"] == "bearish"

    def test_luxalgo_confirmation_plus(self) -> None:
        raw = "TradingView confirmation+|Close:7124.05"
        result = parse_pattern_signal(raw, "LuxAlgo Confirmation+")

        assert result["alert_category"] == "pattern_signal"
        assert result["alert_type"] == "confirmation_plus"
        assert result["price"] == 7124.05
        assert result["pattern_description"] == "TradingView confirmation+"
        assert result["signal_direction"] == "neutral"


class TestParseRawRecord:
    """Tests for parse_raw_record()."""

    def test_skips_test_alert_type(self) -> None:
        row = {
            "id": 1,
            "raw_message": "test",
            "alert_type": "test",
            "received_at": "2026-04-24T10:00:00+00:00",
        }
        result = parse_raw_record(row)
        assert result is None

    def test_fundamentals_record(self) -> None:
        row = {
            "id": 80,
            "raw_message": (
                "Fundamentals|Close:7128.3 |RSI:67.21 |MACD:4.1689 "
                "|Signal:1.0778 |Hist:3.0911 |ADX:15.62 "
                "|VWAP:7126.54 |BB:7127.76-7109.76-7091.76"
            ),
            "alert_type": "fundamentals",
            "received_at": "2026-04-24T13:42:16.116993+00:00",
        }
        result = parse_raw_record(row)

        assert result is not None
        assert result["raw_id"] == 80
        assert result["alert_category"] == "indicator_snapshot"
        assert result["alert_type"] == "fundamentals"
        assert result["price"] == 7128.3
        assert result["rsi"] == 67.21
        assert result["macd"] == 4.1689
        assert result["received_at"] == "2026-04-24T13:42:16.116993+00:00"

    def test_bearish_record(self) -> None:
        row = {
            "id": 79,
            "raw_message": "Bearish reversal +|Close:7126.40",
            "alert_type": "bearish",
            "received_at": "2026-04-24T13:40:01.900546+00:00",
        }
        result = parse_raw_record(row)

        assert result is not None
        assert result["raw_id"] == 79
        assert result["alert_category"] == "pattern_signal"
        assert result["alert_type"] == "bearish_reversal"
        assert result["pattern_description"] == "Bearish reversal +"
        assert result["signal_direction"] == "bearish"
        # Indicator fields should be None
        assert result["rsi"] is None
        assert result["macd"] is None

    def test_overbought_record(self) -> None:
        row = {
            "id": 82,
            "raw_message": "Overbought Hyper Wave oscillator downward signal|Close:7118.95",
            "alert_type": "overbought",
            "received_at": "2026-04-24T13:54:21.251278+00:00",
        }
        result = parse_raw_record(row)

        assert result is not None
        assert result["alert_category"] == "pattern_signal"
        assert result["alert_type"] == "overbought_hyperwave"
        assert result["signal_direction"] == "bearish"

    def test_confirmation_plus_record(self) -> None:
        row = {
            "id": 83,
            "raw_message": "TradingView confirmation+|Close:7124.05",
            "alert_type": "LuxAlgo Confirmation+",
            "received_at": "2026-04-24T14:15:03.442167+00:00",
        }
        result = parse_raw_record(row)

        assert result is not None
        assert result["alert_type"] == "confirmation_plus"
        assert result["signal_direction"] == "neutral"

    def test_unknown_alert_type_returns_unknown_category(self) -> None:
        row = {
            "id": 999,
            "raw_message": "SomeUnknownFormat|Close:7000",
            "alert_type": "unknown_type_xyz",
            "received_at": "2026-04-24T10:00:00+00:00",
        }
        result = parse_raw_record(row)

        assert result is not None
        assert result["alert_category"] == "unknown"
        assert result["alert_type"] == "unknown_type_xyz"
        assert result["metadata"] is not None  # JSON with raw_alert_type


class TestAlertTypeMapping:
    """Tests that _ALERT_TYPE_MAP is complete and consistent."""

    def test_all_known_types_mapped(self) -> None:
        known = {"fundamentals", "bearish", "overbought", "LuxAlgo Confirmation+"}
        assert known == set(_ALERT_TYPE_MAP.keys())

    def test_categories_are_valid(self) -> None:
        for at, (cat, _) in _ALERT_TYPE_MAP.items():
            assert cat in ("indicator_snapshot", "pattern_signal")