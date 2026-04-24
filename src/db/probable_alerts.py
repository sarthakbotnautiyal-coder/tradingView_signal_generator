"""probable_alerts — bundle snapshots/signals around pattern alerts.

When a pattern_signal is inserted into spx_standardized, this module provides
the logic to look back 5 minutes for ALL records (indicator_snapshot and
pattern_signal) and bundle them into the probable_alerts table.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


# ──────────────────────────────────────────────
#  Schema
# ──────────────────────────────────────────────

CREATE_PROBABLE_ALERTS_SQL = """
CREATE TABLE IF NOT EXISTS probable_alerts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_signal_ts       TEXT NOT NULL,
    alert_type              TEXT NOT NULL,
    signal_direction        TEXT NOT NULL,
    price_at_signal         REAL,
    lookback_start          TEXT NOT NULL,
    lookback_end            TEXT NOT NULL,
    bundled_indicators      TEXT NOT NULL,
    indicator_count         INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(pattern_signal_ts)
);
"""


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────

def bundle_indicators(
    db_path: str,
    pattern_signal_ts: datetime,
    lookback_start: datetime,
    lookback_end: datetime,
) -> list[dict[str, Any]]:
    """Query spx_standardized for ALL records in the lookback window.

    Bundles both indicator_snapshot and pattern_signal records so that
    pattern signals carry full context (e.g., a TradingView confirmation+
    preceding a bearish reversal+).

    Args:
        db_path:           Path to tradingview.db
        pattern_signal_ts: EST datetime of the triggering pattern signal
        lookback_start:    Start of lookback window (pattern_signal_ts - 5 min, EST)
        lookback_end:      End of lookback window (pattern_signal_ts, EST, inclusive)

    Returns:
        List of dicts suitable for JSON serialization, ordered by
        received_at ASC. Empty list if no records found.
    """
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, received_at, alert_category, alert_type, price,
               rsi, macd, macd_signal, macd_hist, adx, vwap,
               bb_upper, bb_middle, bb_lower,
               pattern_description, signal_direction
        FROM   spx_standardized
        WHERE  received_at >= :lookback_start
          AND  received_at <= :lookback_end
        ORDER BY received_at ASC
        """,
        {
            "lookback_start": lookback_start.isoformat(),
            "lookback_end":   lookback_end.isoformat(),
        },
    )
    rows = cur.fetchall()
    conn.close()

    bundled: list[dict[str, Any]] = []
    for row in rows:
        (
            id_, received_at, alert_category, alert_type, price,
            rsi, macd, macd_signal, macd_hist, adx, vwap,
            bb_upper, bb_middle, bb_lower,
            pattern_description, signal_direction,
        ) = row
        bundled.append({
            "id":                  id_,
            "received_at":         received_at,
            "alert_category":      alert_category,
            "alert_type":          alert_type,
            "price":               price,
            "rsi":                 rsi,
            "macd":                macd,
            "macd_signal":         macd_signal,
            "macd_hist":           macd_hist,
            "adx":                 adx,
            "vwap":                vwap,
            "bb_upper":            bb_upper,
            "bb_middle":           bb_middle,
            "bb_lower":            bb_lower,
            "pattern_description": pattern_description,
            "signal_direction":    signal_direction,
        })
    return bundled


def create_probable_alert(
    db_path: str,
    pattern_signal_ts: datetime,
    alert_type: str,
    signal_direction: str,
    price_at_signal: float | None,
    lookback_start: datetime,
    lookback_end: datetime,
    bundled: list[dict[str, Any]],
) -> None:
    """Insert a row into probable_alerts.

    Args:
        db_path:             Path to tradingview.db
        pattern_signal_ts:   EST datetime of the triggering pattern signal
        alert_type:          Full description from spx_standardized
                             (e.g. 'Bearish reversal +',
                             'Overbought Hyper Wave oscillator downward signal')
        signal_direction:    'bearish' | 'bullish' | 'neutral'
        price_at_signal:     SPX price at time of pattern signal
        lookback_start:      Start of lookback window (EST)
        lookback_end:        End of lookback window (EST)
        bundled:             Bundled dicts from bundle_indicators() (all types)
    """
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO probable_alerts (
            pattern_signal_ts, alert_type, signal_direction,
            price_at_signal, lookback_start, lookback_end,
            bundled_indicators, indicator_count
        ) VALUES (
            :pattern_signal_ts, :alert_type, :signal_direction,
            :price_at_signal, :lookback_start, :lookback_end,
            :bundled_indicators, :indicator_count
        )
        """,
        {
            "pattern_signal_ts":  pattern_signal_ts.isoformat(),
            "alert_type":        alert_type,
            "signal_direction":  signal_direction,
            "price_at_signal":   price_at_signal,
            "lookback_start":    lookback_start.isoformat(),
            "lookback_end":      lookback_end.isoformat(),
            "bundled_indicators": json.dumps(bundled),
            "indicator_count":    len(bundled),
        },
    )
    conn.commit()
    conn.close()


def compute_lookback_window(pattern_signal_ts: datetime, minutes: int = 5) -> tuple[datetime, datetime]:
    """Compute the lookback window around a pattern signal timestamp.

    Args:
        pattern_signal_ts: EST datetime of the pattern signal
        minutes:           Lookback duration in minutes (default 5)

    Returns:
        (lookback_start, lookback_end) tuple, both EST.
    """
    lookback_end   = pattern_signal_ts
    lookback_start = pattern_signal_ts - timedelta(minutes=minutes)
    return lookback_start, lookback_end
