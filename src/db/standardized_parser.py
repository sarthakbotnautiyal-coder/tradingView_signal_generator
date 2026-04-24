"""Parser for spx_raw → spx_standardized.

Routes raw TradingView alert messages to the correct parser based on alert_type.
"""

import re
import json
from typing import TypedDict

# ──────────────────────────────────────────────
#  Output structures
# ──────────────────────────────────────────────

class ParsedIndicatorSnapshot(TypedDict):
    alert_category: str
    alert_type: str
    symbol: str
    price: float | None
    received_at: str
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    adx: float | None
    vwap: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None


class ParsedPatternSignal(TypedDict):
    alert_category: str
    alert_type: str
    symbol: str
    price: float | None
    received_at: str
    pattern_description: str
    signal_direction: str


# ──────────────────────────────────────────────
#  Alert-type routing
# ──────────────────────────────────────────────

# Maps spx_raw.alert_type → (alert_category, alert_type_in_standardized)
_ALERT_TYPE_MAP: dict[str, tuple[str, str]] = {
    "fundamentals":           ("indicator_snapshot", "fundamentals"),
    "bearish":                ("pattern_signal",     "bearish_reversal"),
    "overbought":             ("pattern_signal",     "overbought_hyperwave"),
    "LuxAlgo Confirmation+":  ("pattern_signal",     "confirmation_plus"),
    # 'test' records are skipped
}

_SKIP_TYPES = {"test"}


def parse_fundamentals(raw_message: str) -> ParsedIndicatorSnapshot:
    """Parse a 'fundamentals' (indicator-snapshot) raw_message.

    Format:
        Fundamentals|Close:7160.44 |RSI:67.46 |MACD:8.2931 |Signal:8.8652
                    |Hist:-0.5721 |ADX:36.96 |VWAP:7135.39
                    |BB:7169.33-7151.42-7133.51

    Returns:
        dict with all indicator fields extracted.
    """
    # Extract close price
    price = _extract_value(r"Close:([\d.]+)", raw_message)

    # Extract indicator values
    rsi         = _extract_value(r"RSI:([-\d.]+)",        raw_message)
    macd        = _extract_value(r"MACD:([-\d.]+)",       raw_message)
    macd_signal = _extract_value(r"Signal:([-\d.]+)",    raw_message)
    macd_hist   = _extract_value(r"Hist:([-\d.]+)",        raw_message)
    adx         = _extract_value(r"ADX:([-\d.]+)",        raw_message)
    vwap        = _extract_value(r"VWAP:([-\d.]+)",       raw_message)

    # Bollinger Bands: "BB:7169.33-7151.42-7133.51" → upper-middle-lower
    bb_match = re.search(r"BB:([\d.]+)-([\d.]+)-([\d.]+)", raw_message)
    if bb_match:
        bb_upper  = float(bb_match.group(1))
        bb_middle = float(bb_match.group(2))
        bb_lower  = float(bb_match.group(3))
    else:
        bb_upper = bb_middle = bb_lower = None

    return ParsedIndicatorSnapshot(
        alert_category="indicator_snapshot",
        alert_type="fundamentals",
        symbol="SPX",
        price=price,
        received_at="",
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        adx=adx,
        vwap=vwap,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
    )


def parse_pattern_signal(raw_message: str, alert_type: str) -> ParsedPatternSignal:
    """Parse a Type-2 pattern-signal raw_message.

    Supported formats:
        Bearish reversal +|Close:7163.18
        Overbought Hyper Wave oscillator downward signal|Close:7156.03
        TradingView confirmation+|Close:7124.05

    Args:
        raw_message: the raw_message from spx_raw
        alert_type:  the alert_type from spx_raw (used for routing/disambiguation)

    Returns:
        dict with pattern_description, signal_direction, and price.
    """
    price = _extract_value(r"Close:([\d.]+)", raw_message)

    # Split on '|' to separate description from price token
    if "|" in raw_message:
        description_part = raw_message.split("|")[0].strip()
    else:
        description_part = raw_message.strip()

    # Determine signal_direction from description text keywords
    description = description_part.lower()

    if "bullish" in description:
        signal_direction = "bullish"
    elif "bearish" in description:
        signal_direction = "bearish"
    elif "overbought" in description or "oversold" in description:
        # Overbought Hyper Wave / Oversold Hyper Wave — extract from keyword
        if "oversold" in description:
            signal_direction = "bullish"
        else:
            signal_direction = "bearish"
    else:
        signal_direction = "neutral"

    return ParsedPatternSignal(
        alert_category="pattern_signal",
        alert_type=_alert_type_key(alert_type),
        symbol="SPX",
        price=price,
        received_at="",
        pattern_description=description_part,
        signal_direction=signal_direction,
    )


def parse_raw_record(row: dict) -> dict | None:
    """Parse a spx_raw row dict into a standardized insert-dict.

    Args:
        row: dict with keys: id, raw_message, alert_type, received_at

    Returns:
        Flat dict ready for INSERT into spx_standardized, or None if skipped.
    """
    raw_id      = row["id"]
    raw_message = row["raw_message"]
    alert_type  = row["alert_type"]
    received_at = row["received_at"]

    # Route
    if alert_type in _SKIP_TYPES:
        return None

    if alert_type not in _ALERT_TYPE_MAP:
        # Unknown type — return minimal record with metadata
        return dict(
            raw_id=raw_id,
            alert_category="unknown",
            alert_type=alert_type,
            symbol="SPX",
            price=_extract_value(r"Close:([\d.]+)", raw_message),
            received_at=received_at,
            rsi=None, macd=None, macd_signal=None, macd_hist=None,
            adx=None, vwap=None, bb_upper=None, bb_middle=None, bb_lower=None,
            pattern_description=None,
            signal_direction=None,
            metadata=json.dumps({"raw_alert_type": alert_type}),
            processed=0,
        )

    category, _ = _ALERT_TYPE_MAP[alert_type]

    if category == "indicator_snapshot":
        result: dict = parse_fundamentals(raw_message)
        result["raw_id"]              = raw_id
        result["received_at"]         = received_at
        result["metadata"]            = None
        result["processed"]           = 0
        # Pattern-signal fields are NULL for indicator snapshots
        result["pattern_description"]  = None
        result["signal_direction"]    = None
        return result

    else:   # pattern_signal
        result: dict = parse_pattern_signal(raw_message, alert_type)
        result["raw_id"]      = raw_id
        result["received_at"] = received_at
        # None out indicator fields for pattern signals
        result["rsi"]         = None
        result["macd"]        = None
        result["macd_signal"] = None
        result["macd_hist"]   = None
        result["adx"]         = None
        result["vwap"]        = None
        result["bb_upper"]    = None
        result["bb_middle"]   = None
        result["bb_lower"]    = None
        result["metadata"]    = None
        result["processed"]   = 0
        return result


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────

_ALERT_TYPE_KEY_MAP = {v: k for k, v in _ALERT_TYPE_MAP.items()}


def _alert_type_key(raw_alert_type: str) -> str:
    """Map raw spx_raw alert_type to the standardized alert_type string."""
    if raw_alert_type in _ALERT_TYPE_MAP:
        return _ALERT_TYPE_MAP[raw_alert_type][1]
    return raw_alert_type


def _extract_value(pattern: str, text: str) -> float | None:
    """Extract first float match; return None if not found."""
    m = re.search(pattern, text)
    if m:
        return float(m.group(1))
    return None