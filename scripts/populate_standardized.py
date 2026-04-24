#!/usr/bin/env python3
"""Populate spx_standardized from unprocessed rows in spx_raw.

Run manually or via cron after market close:
    0 17 * * 1-5 cd /Users/ubexbot/.openclaw/workspace-venkat/tradingView_signal_generator \
        && /opt/homebrew/bin/python3 scripts/populate_standardized.py >> logs/standardized_populate.log 2>&1

The script:
  1. Reads all unprocessed rows from spx_raw (WHERE processed = 0)
  2. Parses each row using src.db.standardized_parser
  3. Bulk-inserts into spx_standardized
  4. Marks spx_raw.processed = 1 for successfully parsed rows
  5. Logs: processed count, skipped count, any errors
"""

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.standardized_parser import parse_raw_record

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "logs" / "standardized_populate.log"),
    ],
)
log = logging.getLogger("populate_standardized")

# ── Database ─────────────────────────────────────────────────────────────────

DB_PATH = PROJECT_ROOT / "data" / "tradingview.db"

# ── Schema ───────────────────────────────────────────────────────────────────

CREATE_STANDARDIZED_SQL = """
CREATE TABLE IF NOT EXISTS spx_standardized (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_id              INTEGER NOT NULL,
    alert_category      TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    symbol              TEXT,
    price               REAL,
    received_at         TEXT NOT NULL,
    -- indicator_snapshot fields
    rsi                 REAL,
    macd                REAL,
    macd_signal         REAL,
    macd_hist           REAL,
    adx                 REAL,
    vwap                REAL,
    bb_upper            REAL,
    bb_middle           REAL,
    bb_lower            REAL,
    -- pattern_signal fields
    pattern_description  TEXT,
    signal_direction     TEXT,
    -- extensibility
    metadata            TEXT,
    -- processing
    processed           INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (raw_id) REFERENCES spx_raw(id)
);
"""

CREATE_RAW_PROCESSED_SQL = """
CREATE TABLE IF NOT EXISTS spx_raw (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_message     TEXT NOT NULL,
    alert_type      TEXT,
    symbol          TEXT,
    price           REAL,
    received_at     TEXT NOT NULL,
    processed       INTEGER DEFAULT 0
);
"""

UPSERT_SQL = """
INSERT INTO spx_standardized (
    raw_id, alert_category, alert_type, symbol, price, received_at,
    rsi, macd, macd_signal, macd_hist, adx, vwap,
    bb_upper, bb_middle, bb_lower,
    pattern_description, signal_direction,
    metadata, processed
) VALUES (
    :raw_id, :alert_category, :alert_type, :symbol, :price, :received_at,
    :rsi, :macd, :macd_signal, :macd_hist, :adx, :vwap,
    :bb_upper, :bb_middle, :bb_lower,
    :pattern_description, :signal_direction,
    :metadata, :processed
);
"""

MARK_PROCESSED_SQL = """
UPDATE spx_raw SET processed = 1 WHERE id = :id;
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create spx_standardized table if it doesn't exist."""
    cur = conn.cursor()
    cur.execute(CREATE_STANDARDIZED_SQL)
    # If spx_raw doesn't have 'processed' column, add it
    try:
        cur.execute("SELECT processed FROM spx_raw LIMIT 1")
    except sqlite3.OperationalError:
        log.warning("spx_raw missing 'processed' column — adding it")
        cur.execute("ALTER TABLE spx_raw ADD COLUMN processed INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE spx_raw ADD COLUMN symbol TEXT")
        cur.execute("ALTER TABLE spx_raw ADD COLUMN price REAL")
    conn.commit()
    log.info("Schema check complete.")


def populate(db_path: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """Fetch unprocessed spx_raw rows, parse, insert into spx_standardized.

    Returns:
        (processed, skipped, errors)
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    ensure_schema(conn)

    # Fetch unprocessed rows
    cur = conn.cursor()
    cur.execute("SELECT id, raw_message, alert_type, received_at FROM spx_raw WHERE processed = 0")
    rows = cur.fetchall()
    log.info("Found %d unprocessed rows in spx_raw.", len(rows))

    processed = 0
    skipped   = 0
    errors    = 0

    for row in rows:
        row_dict = dict(row)
        try:
            parsed = parse_raw_record(row_dict)
        except Exception as exc:
            log.error("Parse error for spx_raw id=%d: %s", row["id"], exc)
            errors += 1
            continue

        if parsed is None:
            log.debug("Skipped spx_raw id=%d (alert_type=%s)", row["id"], row["alert_type"])
            skipped += 1
            # Mark as processed so we don't re-read
            cur.execute(MARK_PROCESSED_SQL, {"id": row["id"]})
            conn.commit()
            continue

        if dry_run:
            log.info("[DRY RUN] Would insert: %s", parsed)
            processed += 1
            continue

        try:
            cur.execute(UPSERT_SQL, parsed)
            cur.execute(MARK_PROCESSED_SQL, {"id": row["id"]})
            conn.commit()
            processed += 1
        except sqlite3.Error as exc:
            log.error("DB error inserting spx_raw id=%d: %s", row["id"], exc)
            errors += 1

    conn.close()
    return processed, skipped, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate spx_standardized from spx_raw")
    parser.add_argument("--db", type=Path, default=DB_PATH,
                        help="Path to tradingview.db")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse but don't insert; log what would be inserted")
    args = parser.parse_args()

    log.info("=== spx_standardized population run at %s ===",
             datetime.now(timezone.utc).isoformat())

    # Ensure logs dir exists
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)

    if not args.db.exists():
        log.error("Database not found: %s", args.db)
        sys.exit(1)

    processed, skipped, errors = populate(args.db, dry_run=args.dry_run)

    log.info("Done. processed=%d skipped=%d errors=%d", processed, skipped, errors)

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()