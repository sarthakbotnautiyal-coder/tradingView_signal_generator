"""Telethon listener for TradingView alerts from private Telegram channel.

Logs every raw message to SQLite (data/tradingview.db → spx_raw table).
alert_type is derived from message prefix (LuxAlgo, TradingView, etc.).
Auto-shuts down at 4PM EST on weekdays.

Inline population: every incoming message is immediately parsed and inserted
into spx_standardized — no separate populate script needed.

probable_alerts: when a pattern_signal is inserted, look back 5 minutes in
spx_standardized for indicator_snapshot records and bundle them into
probable_alerts.
"""

import logging
import re
import sqlite3
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from telethon import TelegramClient
from telethon.events import NewMessage

from src.db.probable_alerts import (
    CREATE_PROBABLE_ALERTS_SQL,
    bundle_indicators,
    create_probable_alert,
    compute_lookback_window,
)
from src.db.standardized_parser import parse_raw_record

logger = logging.getLogger(__name__)

EST = ZoneInfo("America/New_York")
SHUTDOWN_TIME = time(16, 0)  # 4:00 PM EST


# ──────────────────────────────────────────────
#  Schema SQL
# ──────────────────────────────────────────────

CREATE_SPX_STANDARDIZED_SQL = """
CREATE TABLE IF NOT EXISTS spx_standardized (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_id                  INTEGER NOT NULL,
    alert_category          TEXT NOT NULL,
    alert_type              TEXT NOT NULL,
    symbol                  TEXT,
    price                   REAL,
    received_at             TEXT NOT NULL,
    -- indicator_snapshot fields (Type 1)
    rsi                     REAL,
    macd                    REAL,
    macd_signal             REAL,
    macd_hist               REAL,
    adx                     REAL,
    vwap                    REAL,
    bb_upper                REAL,
    bb_middle               REAL,
    bb_lower                REAL,
    -- pattern_signal fields (Type 2)
    pattern_description     TEXT,
    signal_direction        TEXT,
    -- extensibility
    metadata                TEXT,
    processed               INTEGER DEFAULT 0,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

UPSERT_STANDARDIZED_SQL = """
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


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def in_market_hours(now_est: datetime) -> bool:
    """Return True if within trading hours (9:30 AM–4:00 PM ET, Mon–Fri)."""
    if now_est.weekday() >= 5:
        return False
    market_start = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
    market_end = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_start <= now_est <= market_end


def should_shutdown(now_est: datetime) -> bool:
    """Return True if it's past 4PM EST on a weekday."""
    if now_est.weekday() >= 5:
        return False
    return now_est.time() >= SHUTDOWN_TIME


def classify_alert_type(text: str) -> str:
    """Classify alert type from message prefix."""
    text = text.strip()
    if text.startswith("TradingView exit") or text.startswith("LuxAlgo Exit"):
        return "LuxAlgo Exit"
    if text.startswith("TradingView confirmation+") or text.startswith("LuxAlgo Confirmation+"):
        return "LuxAlgo Confirmation+"
    if text.startswith("RSI:") or text.startswith("LuxAlgo RSI") or text.startswith("LuxAlgo"):
        return "Fundamentals"
    if text.startswith("TradingView Alert"):
        return "tradingview"
    # Generic fallback: use first word up to common delimiters
    prefix = re.split(r"[\s:\-|]", text)[0].strip()
    return prefix.lower() if prefix else "unknown"


# ──────────────────────────────────────────────
#  Listener
# ──────────────────────────────────────────────

class Listener:
    """Listens to a private Telegram channel for TradingView alert messages."""

    def __init__(
        self,
        api_id: str,
        api_hash: str,
        phone: str,
        channel_entity: str,
        session_name: str = "listener_session",
        sessions_dir: str = "sessions",
        db_path: str = "data/tradingview.db",
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.channel_entity = channel_entity
        self.session_name = session_name
        self.sessions_dir = Path(sessions_dir)
        self.db_path = Path(db_path)

        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Ensure DB and tables exist
        self._init_db()

    def _init_db(self) -> None:
        """Create spx_raw and spx_standardized tables; truncate spx_raw on startup."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()

        # TASK-2026-082: Truncate spx_raw on every listener startup for a clean daily start
        cur.execute("DELETE FROM spx_raw")
        logger.info("spx_raw table truncated — fresh daily start.")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS spx_raw (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_message     TEXT NOT NULL,
                alert_type      TEXT,
                symbol          TEXT,
                price           REAL,
                received_at     TEXT NOT NULL,
                processed       INTEGER DEFAULT 0
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_spx_raw_received ON spx_raw(received_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_spx_raw_alert_type ON spx_raw(alert_type)")

        # spx_standardized — created once, reused across restarts
        cur.execute(CREATE_SPX_STANDARDIZED_SQL)

        # probable_alerts — created once, reused across restarts
        cur.execute(CREATE_PROBABLE_ALERTS_SQL)

        conn.commit()
        conn.close()

    def _get_session_path(self) -> Path:
        return self.sessions_dir / f"{self.session_name}.session"

    def _insert_raw(self, raw_message: str, alert_type: str) -> int:
        """Insert a raw message into spx_raw table. Returns row ID."""
        now_est = datetime.now(EST).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO spx_raw (raw_message, alert_type, received_at) VALUES (?, ?, ?)",
            (raw_message, alert_type, now_est),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def _insert_standardized(self, raw_id: int, parsed: dict) -> int:
        """Insert a parsed record into spx_standardized. Returns row ID."""
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute(UPSERT_STANDARDIZED_SQL, parsed)
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def _maybe_create_probable_alert(self, pattern_signal_ts: datetime) -> None:
        """Look back 5 minutes for indicator snapshots; bundle into probable_alerts if found.

        Args:
            pattern_signal_ts: EST datetime of the pattern signal just inserted.
        """
        lookback_start, lookback_end = compute_lookback_window(pattern_signal_ts)
        indicators = bundle_indicators(
            str(self.db_path), pattern_signal_ts, lookback_start, lookback_end
        )
        if not indicators:
            logger.info(
                f"[probable_alerts] no indicators in lookback window "
                f"({lookback_start.isoformat()} – {lookback_end.isoformat()}), skipping."
            )
            return

        # Fetch alert metadata from spx_standardized
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT alert_type, signal_direction, price
            FROM   spx_standardized
            WHERE  alert_category = 'pattern_signal'
              AND  received_at = :ts
            LIMIT 1
            """,
            {"ts": pattern_signal_ts.isoformat()},
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            logger.warning(f"[probable_alerts] pattern_signal not found at {pattern_signal_ts}")
            return

        alert_type, signal_direction, price = row
        create_probable_alert(
            str(self.db_path),
            pattern_signal_ts,
            alert_type,
            signal_direction,
            price,
            lookback_start,
            lookback_end,
            indicators,
        )
        logger.info(
            f"[probable_alerts] created alert for pattern_signal_ts={pattern_signal_ts.isoformat()} "
            f"with {len(indicators)} indicator(s)."
        )

    async def _resolve_channel(self, client: TelegramClient):
        """Resolve channel entity from name, username, or numeric chat_id."""
        try:
            entity = await client.get_entity(self.channel_entity)
            logger.info(f"Channel resolved directly: {self.channel_entity}")
            return entity
        except ValueError:
            pass

        channel_id = int(self.channel_entity)
        logger.info(f"Scanning dialogs for channel id {channel_id}...")
        async for dialog in client.iter_dialogs():
            if dialog.id == channel_id:
                logger.info(f"Channel found in dialogs: {dialog.name} (id={dialog.id})")
                return dialog.entity

        raise ValueError(
            f"Could not find channel with id '{self.channel_entity}' in your dialogs."
        )

    async def handle_message(self, event: NewMessage) -> None:
        """Handle incoming message from the channel.

        Flow per message:
          classify_alert_type()
          → _insert_raw()                  → spx_raw
          → parse_raw_record()             → dict with all standardized fields
          → _insert_standardized()          → spx_standardized
          → _maybe_create_probable_alert()  → probable_alerts (pattern signals only)
          → logger.info(...)
        """
        message_text = event.message.message or ""
        if not message_text.strip():
            return

        alert_type = classify_alert_type(message_text)
        received_at = datetime.now(EST)
        received_at_iso = received_at.isoformat()
        raw_id = self._insert_raw(message_text.strip(), alert_type)

        # Build row dict for parser
        row = {
            "id": raw_id,
            "raw_message": message_text.strip(),
            "alert_type": alert_type,
            "received_at": received_at_iso,
        }

        parsed = parse_raw_record(row)
        if parsed is not None:
            self._insert_standardized(raw_id, parsed)
            logger.info(
                f"[{alert_type}] raw={raw_id} standardized_id={parsed.get('id', '?')} | "
                f"{message_text.strip()[:80]}"
            )
            # Trigger probable_alerts bundling for pattern signals
            if parsed.get("alert_category") == "pattern_signal":
                self._maybe_create_probable_alert(received_at)
        else:
            logger.info(
                f"[{alert_type}] raw={raw_id} [skipped] | {message_text.strip()[:80]}"
            )

        # Auto-shutdown check
        now_est = datetime.now(EST)
        if should_shutdown(now_est):
            logger.info(f"4PM EST reached — shutting down listener.")
            await event.client.disconnect()
            return

    async def run(self) -> None:
        """Connect to Telegram and start listening to the channel."""
        now_est = datetime.now(EST)
        if not in_market_hours(now_est):
            logger.info(
                f"Outside market hours (now={now_est.strftime('%H:%M')} ET). "
                "Listener will start and wait for messages during market hours."
            )

        client = TelegramClient(
            str(self._get_session_path()),
            self.api_id,
            self.api_hash,
        )

        await client.start(phone=self.phone)
        logger.info(f"Connected to Telegram as {self.phone}")

        channel = await self._resolve_channel(client)
        channel_title = getattr(channel, "title", self.channel_entity)
        logger.info(f"Listening on channel: {channel_title}")
        logger.info(f"Auto-shutdown scheduled for 4:00 PM EST on weekdays.")

        client.add_event_handler(
            self.handle_message,
            NewMessage(chats=[channel]),
        )
        logger.info("Listener started. Press Ctrl+C to stop.")
        await client.run_until_disconnected()


def run_listener(config_path: str = "config/config.yaml") -> None:
    """Run the listener from config file."""
    import yaml

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    telegram_cfg = config.get("telegram", {})
    channel_cfg = config.get("channel", {})

    channel_entity = channel_cfg.get("entity", "-1003946119741")

    listener = Listener(
        api_id=str(telegram_cfg.get("api_id", "")),
        api_hash=telegram_cfg.get("api_hash", ""),
        phone=telegram_cfg.get("phone", ""),
        channel_entity=channel_entity,
        session_name=telegram_cfg.get("session_name", "listener_session"),
        sessions_dir=telegram_cfg.get("sessions_dir", "sessions"),
        db_path="data/tradingview.db",
    )

    import asyncio
    asyncio.run(listener.run())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s,%(levelname)s %(name)s: %(message)s",
    )
    run_listener()
