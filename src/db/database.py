"""SQLite database for alert logging."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .parser import AlertMessage


class AlertDatabase:
    """SQLite database for storing parsed TradingView alerts."""

    def __init__(self, db_path: str = "alert_log.db"):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_message     TEXT NOT NULL,
                    symbol          TEXT,
                    price           REAL,
                    received_at     TEXT NOT NULL,
                    processed       INTEGER DEFAULT 0,
                    phase           INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alert_symbol
                ON alert_log(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alert_received
                ON alert_log(received_at)
            """)
            conn.commit()

    @contextmanager
    def _get_conn(self):
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def insert_alert(self, alert: AlertMessage) -> int:
        """Insert a parsed alert into the database.

        Args:
            alert: Parsed AlertMessage object.

        Returns:
            Row ID of inserted alert.
        """
        received = alert.timestamp.isoformat() if alert.timestamp else datetime.now(timezone.utc).isoformat()

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO alert_log (raw_message, symbol, price, received_at, processed, phase)
                VALUES (?, ?, ?, ?, 0, 1)
                """,
                (alert.raw_text, alert.symbol, alert.price, received),
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_alerts(self, limit: int = 10) -> list[dict]:
        """Fetch recent alerts for debugging/monitoring."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_log ORDER BY received_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]


# Module-level singleton
_db: Optional[AlertDatabase] = None


def get_database(db_path: str = "alert_log.db") -> AlertDatabase:
    """Get or create database singleton."""
    global _db
    if _db is None:
        _db = AlertDatabase(db_path)
    return _db