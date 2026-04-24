"""Unit tests for src.db.probable_alerts — lookback bundling logic."""

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from src.db.probable_alerts import (
    CREATE_PROBABLE_ALERTS_SQL,
    bundle_indicators,
    compute_lookback_window,
    create_probable_alert,
)


# ──────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path: pytest.ImportPath) -> str:
    """In-memory DB with spx_standardized + probable_alerts schema."""
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    # spx_standardized schema (mirrors listener.py)
    cur.execute("""
        CREATE TABLE spx_standardized (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_id                  INTEGER NOT NULL,
            alert_category          TEXT NOT NULL,
            alert_type              TEXT NOT NULL,
            symbol                  TEXT,
            price                   REAL,
            received_at             TEXT NOT NULL,
            rsi                     REAL,
            macd                    REAL,
            macd_signal             REAL,
            macd_hist               REAL,
            adx                     REAL,
            vwap                    REAL,
            bb_upper                REAL,
            bb_middle               REAL,
            bb_lower                REAL,
            pattern_description     TEXT,
            signal_direction        TEXT,
            metadata                TEXT,
            processed               INTEGER DEFAULT 0,
            created_at              TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # probable_alerts schema
    cur.execute(CREATE_PROBABLE_ALERTS_SQL)

    conn.commit()
    conn.close()
    return path


def _insert_standardized(
    db_path: str,
    alert_category: str,
    alert_type: str,
    received_at: datetime,
    price: float | None = None,
    rsi: float | None = None,
    macd: float | None = None,
    pattern_description: str | None = None,
    signal_direction: str | None = None,
) -> int:
    """Helper to insert a row into spx_standardized."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO spx_standardized (
            raw_id, alert_category, alert_type, symbol, price, received_at,
            rsi, macd, macd_signal, macd_hist, adx, vwap,
            bb_upper, bb_middle, bb_lower,
            pattern_description, signal_direction,
            metadata, processed
        ) VALUES (
            1, :alert_category, :alert_type, 'SPX', :price, :received_at,
            :rsi, :macd, NULL, NULL, NULL, NULL,
            NULL, NULL, NULL,
            :pattern_description, :signal_direction,
            NULL, 0
        )
        """,
        {
            "alert_category":     alert_category,
            "alert_type":         alert_type,
            "price":              price,
            "received_at":        received_at.isoformat(),
            "rsi":                rsi,
            "macd":               macd,
            "pattern_description": pattern_description,
            "signal_direction":   signal_direction,
        },
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


# ──────────────────────────────────────────────
#  compute_lookback_window
# ──────────────────────────────────────────────

class TestComputeLookbackWindow:
    def test_default_5_minutes(self) -> None:
        ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        start, end = compute_lookback_window(ts)
        assert start == datetime(2026, 4, 24, 16, 25, 0, tzinfo=timezone.utc)
        assert end   == datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)

    def test_custom_minutes(self) -> None:
        ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        start, end = compute_lookback_window(ts, minutes=3)
        assert start == datetime(2026, 4, 24, 16, 27, 0, tzinfo=timezone.utc)


# ──────────────────────────────────────────────
#  bundle_indicators — all alert types bundled
# ──────────────────────────────────────────────

class TestBundleIndicators:
    def test_no_records_in_window(self, db_path: str) -> None:
        """Pattern signal with 0 records in window → empty list."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        # Insert indicator outside window
        _insert_standardized(
            db_path, "indicator_snapshot", "fundamentals",
            datetime(2026, 4, 24, 16, 20, 0, tzinfo=timezone.utc),
            price=7100.0, rsi=60.0, macd=1.0,
        )

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert result == []

    def test_one_indicator_in_window(self, db_path: str) -> None:
        """Pattern signal with 1 indicator in window → list with 1 item."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        ind_ts = datetime(2026, 4, 24, 16, 27, 0, tzinfo=timezone.utc)
        ind_id = _insert_standardized(
            db_path, "indicator_snapshot", "fundamentals",
            ind_ts, price=7100.0, rsi=67.46, macd=8.2931,
        )

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 1
        assert result[0]["id"] == ind_id
        assert result[0]["rsi"] == 67.46
        assert result[0]["macd"] == 8.2931

    def test_multiple_indicators_in_window(self, db_path: str) -> None:
        """Pattern signal with 3 indicators in window → list with 3 items, ordered ASC."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        ind1_ts = datetime(2026, 4, 24, 16, 26, 0, tzinfo=timezone.utc)
        ind2_ts = datetime(2026, 4, 24, 16, 28, 0, tzinfo=timezone.utc)
        ind3_ts = datetime(2026, 4, 24, 16, 29, 0, tzinfo=timezone.utc)

        ind1_id = _insert_standardized(db_path, "indicator_snapshot", "fundamentals", ind1_ts, price=7100.0, rsi=60.0)
        ind2_id = _insert_standardized(db_path, "indicator_snapshot", "fundamentals", ind2_ts, price=7101.0, rsi=65.0)
        ind3_id = _insert_standardized(db_path, "indicator_snapshot", "fundamentals", ind3_ts, price=7102.0, rsi=70.0)

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 3
        assert result[0]["id"] == ind1_id
        assert result[1]["id"] == ind2_id
        assert result[2]["id"] == ind3_id
        assert result[0]["rsi"] == 60.0
        assert result[2]["rsi"] == 70.0

    def test_edge_of_window_inclusive_start(self, db_path: str) -> None:
        """Indicator at exactly lookback_start is included."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        ind_ts = datetime(2026, 4, 24, 16, 25, 0, tzinfo=timezone.utc)
        _insert_standardized(db_path, "indicator_snapshot", "fundamentals", ind_ts, price=7100.0, rsi=60.0)

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 1

    def test_edge_of_window_inclusive_end(self, db_path: str) -> None:
        """Indicator at exactly lookback_end is included."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        ind_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        _insert_standardized(db_path, "indicator_snapshot", "fundamentals", ind_ts, price=7100.0, rsi=60.0)

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 1

    def test_includes_pattern_signals_in_window(self, db_path: str) -> None:
        """Pattern signals ARE now included in the bundle (was: excluded)."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        _insert_standardized(db_path, "indicator_snapshot", "fundamentals",
                             datetime(2026, 4, 24, 16, 28, 0, tzinfo=timezone.utc),
                             price=7100.0, rsi=60.0)
        # This confirmation_plus pattern signal should NOW appear in bundle
        _insert_standardized(db_path, "pattern_signal", "confirmation_plus",
                             datetime(2026, 4, 24, 16, 29, 0, tzinfo=timezone.utc),
                             price=7163.18,
                             pattern_description="TradingView confirmation+",
                             signal_direction="neutral")

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 2
        indicator_record = result[0]
        pattern_record   = result[1]
        assert indicator_record["alert_category"] == "indicator_snapshot"
        assert pattern_record["alert_category"]  == "pattern_signal"
        assert pattern_record["alert_type"]      == "confirmation_plus"
        assert pattern_record["price"]           == 7163.18
        assert pattern_record["pattern_description"] == "TradingView confirmation+"
        assert pattern_record["signal_direction"]    == "neutral"

    def test_alert_category_and_type_always_present(self, db_path: str) -> None:
        """Every bundled record — indicator or pattern — always has alert_category and alert_type."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        _insert_standardized(db_path, "indicator_snapshot", "fundamentals",
                             datetime(2026, 4, 24, 16, 28, 0, tzinfo=timezone.utc),
                             price=7100.0, rsi=60.0)
        _insert_standardized(db_path, "pattern_signal", "bearish_reversal",
                             datetime(2026, 4, 24, 16, 29, 0, tzinfo=timezone.utc),
                             price=7163.18,
                             pattern_description="Bearish reversal+",
                             signal_direction="bearish")

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 2
        for record in result:
            assert "alert_category" in record
            assert "alert_type"      in record
            assert "price"           in record

    def test_pattern_signal_plus_indicator_bundle(self, db_path: str) -> None:
        """Pattern signal with 1 indicator_snapshot + 1 pattern_signal → both bundled."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        _insert_standardized(db_path, "indicator_snapshot", "fundamentals",
                             datetime(2026, 4, 24, 16, 27, 0, tzinfo=timezone.utc),
                             price=7100.0, rsi=60.0, macd=1.0)
        _insert_standardized(db_path, "pattern_signal", "confirmation_plus",
                             datetime(2026, 4, 24, 16, 28, 30, tzinfo=timezone.utc),
                             price=7160.00,
                             pattern_description="TradingView confirmation+",
                             signal_direction="neutral")

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 2
        assert result[0]["alert_category"] == "indicator_snapshot"
        assert result[1]["alert_category"] == "pattern_signal"
        assert result[1]["alert_type"] == "confirmation_plus"

    def test_pattern_signal_with_only_pattern_signals_in_window(self, db_path: str) -> None:
        """Pattern signal with only pattern_signals (no indicators) in window → bundle count > 0."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        # Two confirmation_plus signals in the window, no indicators
        _insert_standardized(db_path, "pattern_signal", "confirmation_plus",
                             datetime(2026, 4, 24, 16, 27, 0, tzinfo=timezone.utc),
                             price=7155.0,
                             pattern_description="TradingView confirmation+",
                             signal_direction="neutral")
        _insert_standardized(db_path, "pattern_signal", "confirmation_plus",
                             datetime(2026, 4, 24, 16, 29, 0, tzinfo=timezone.utc),
                             price=7158.0,
                             pattern_description="TradingView confirmation+",
                             signal_direction="neutral")

        result = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(result) == 2
        for record in result:
            assert record["alert_category"] == "pattern_signal"


# ──────────────────────────────────────────────
#  create_probable_alert
# ──────────────────────────────────────────────

class TestCreateProbableAlert:
    def test_inserts_row_with_bundled_records(self, db_path: str) -> None:
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)
        bundled = [{
            "id": 10, "alert_category": "indicator_snapshot",
            "alert_type": "fundamentals", "price": 7100.0,
            "rsi": 67.46, "macd": 8.2931,
            "macd_signal": None, "macd_hist": None,
            "adx": None, "vwap": None,
            "bb_upper": None, "bb_middle": None, "bb_lower": None,
            "pattern_description": None, "signal_direction": None,
            "received_at": "2026-04-24T16:27:00+00:00",
        }]

        create_probable_alert(
            db_path,
            pattern_ts,
            "bearish_reversal",
            "bearish",
            7163.18,
            lookback_start,
            lookback_end,
            bundled,
        )

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT * FROM probable_alerts")
        rows = cur.fetchall()
        conn.close()

        assert len(rows) == 1
        # id=1, pattern_signal_ts, alert_type, signal_direction, price_at_signal,
        # lookback_start, lookback_end, bundled_indicators, indicator_count, created_at
        assert rows[0][1] == pattern_ts.isoformat()
        assert rows[0][2] == "bearish_reversal"
        assert rows[0][3] == "bearish"
        assert rows[0][4] == 7163.18
        assert rows[0][8] == 1  # indicator_count (== len(bundled))

        bundled_stored = json.loads(rows[0][7])
        assert len(bundled_stored) == 1
        assert bundled_stored[0]["rsi"] == 67.46

    def test_ignores_duplicate_same_timestamp(self, db_path: str) -> None:
        """UNIQUE constraint on pattern_signal_ts prevents duplicate inserts."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)
        bundled = [{"id": 10, "rsi": 67.46}]

        create_probable_alert(
            db_path, pattern_ts, "bearish_reversal", "bearish", 7163.18,
            lookback_start, lookback_end, bundled,
        )
        # Second call with same pattern_signal_ts — should be ignored (no exception)
        create_probable_alert(
            db_path, pattern_ts, "bearish_reversal", "bearish", 7163.18,
            lookback_start, lookback_end, bundled,
        )

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM probable_alerts")
        count = cur.fetchone()[0]
        conn.close()

        assert count == 1

    def test_indicator_count_reflects_bundle_length(self, db_path: str) -> None:
        """indicator_count is len(bundled) even when bundle contains mixed types."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)
        bundled = [
            {"id": 10, "alert_category": "indicator_snapshot", "alert_type": "fundamentals"},
            {"id": 11, "alert_category": "pattern_signal",    "alert_type": "confirmation_plus"},
            {"id": 12, "alert_category": "pattern_signal",    "alert_type": "bearish_reversal"},
        ]

        create_probable_alert(
            db_path, pattern_ts, "overbought_hyperwave", "bearish", 7156.03,
            lookback_start, lookback_end, bundled,
        )

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT indicator_count, bundled_indicators FROM probable_alerts")
        row = cur.fetchone()
        conn.close()

        assert row[0] == 3
        bundled_stored = json.loads(row[1])
        assert len(bundled_stored) == 3


# ──────────────────────────────────────────────
#  Integration-style: full pattern signal flow
# ──────────────────────────────────────────────

class TestProbableAlertsFullFlow:
    def test_pattern_signal_no_records_skipped(self, db_path: str) -> None:
        """Pattern signal with 0 records in window → no row created."""
        # Insert indicator at 16:20, pattern signal at 16:30 (outside 5-min window)
        _insert_standardized(
            db_path, "indicator_snapshot", "fundamentals",
            datetime(2026, 4, 24, 16, 20, 0, tzinfo=timezone.utc),
            price=7100.0, rsi=60.0,
        )

        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        bundled = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert bundled == []

        # No create_probable_alert call when count == 0
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM probable_alerts")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0

    def test_pattern_signal_with_records_row_created(self, db_path: str) -> None:
        """Pattern signal with ≥1 record in window → row created."""
        # Insert indicator in the window
        ind_ts1 = datetime(2026, 4, 24, 16, 27, 0, tzinfo=timezone.utc)
        ind_ts2 = datetime(2026, 4, 24, 16, 29, 0, tzinfo=timezone.utc)
        _insert_standardized(db_path, "indicator_snapshot", "fundamentals",
                             ind_ts1, price=7100.0, rsi=60.0)
        _insert_standardized(db_path, "indicator_snapshot", "fundamentals",
                             ind_ts2, price=7101.0, rsi=65.0)

        # Pattern signal triggers the bundling
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        bundled = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(bundled) == 2

        create_probable_alert(
            db_path, pattern_ts, "confirmation_plus", "neutral", 7124.05,
            lookback_start, lookback_end, bundled,
        )

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT alert_type, signal_direction, indicator_count FROM probable_alerts")
        row = cur.fetchone()
        conn.close()

        assert row[0] == "confirmation_plus"
        assert row[1] == "neutral"
        assert row[2] == 2

    def test_full_flow_mixed_types_bundled(self, db_path: str) -> None:
        """End-to-end: 2 indicators + 1 pattern signal in window → all 3 bundled."""
        pattern_ts = datetime(2026, 4, 24, 16, 30, 0, tzinfo=timezone.utc)
        lookback_start, lookback_end = compute_lookback_window(pattern_ts)

        _insert_standardized(db_path, "indicator_snapshot", "fundamentals",
                             datetime(2026, 4, 24, 16, 26, 0, tzinfo=timezone.utc),
                             price=7100.0, rsi=60.0, macd=1.0)
        _insert_standardized(db_path, "indicator_snapshot", "fundamentals",
                             datetime(2026, 4, 24, 16, 28, 0, tzinfo=timezone.utc),
                             price=7105.0, rsi=65.0, macd=1.5)
        _insert_standardized(db_path, "pattern_signal", "confirmation_plus",
                             datetime(2026, 4, 24, 16, 29, 30, tzinfo=timezone.utc),
                             price=7160.0,
                             pattern_description="TradingView confirmation+",
                             signal_direction="neutral")

        bundled = bundle_indicators(db_path, pattern_ts, lookback_start, lookback_end)
        assert len(bundled) == 3

        create_probable_alert(
            db_path, pattern_ts, "bearish_reversal", "bearish", 7163.18,
            lookback_start, lookback_end, bundled,
        )

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT indicator_count, bundled_indicators FROM probable_alerts")
        row = cur.fetchone()
        conn.close()

        assert row[0] == 3
        stored = json.loads(row[1])
        categories = [r["alert_category"] for r in stored]
        assert categories == ["indicator_snapshot", "indicator_snapshot", "pattern_signal"]
        pattern_record = next(r for r in stored if r["alert_category"] == "pattern_signal")
        assert pattern_record["alert_type"] == "confirmation_plus"
        assert pattern_record["price"] == 7160.0