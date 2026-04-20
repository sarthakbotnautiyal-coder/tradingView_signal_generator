"""Telethon listener for TradingView alerts from private Telegram channel."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

from .parser import AlertParser, AlertMessage
from .db import get_database

logger = logging.getLogger(__name__)


class TradingViewListener:
    """Listens to a private Telegram channel for TradingView alert messages."""

    def __init__(
        self,
        api_id: str,
        api_hash: str,
        phone: str,
        channel_entity: str,
        session_name: str = "listener_session",
        sessions_dir: str = "sessions",
        alerts_log_path: str = "alerts.log",
    ):
        """Initialize the listener.

        Args:
            api_id: Telegram API ID.
            api_hash: Telegram API Hash.
            phone: Telegram phone number.
            channel_entity: Channel name or username to listen on.
            session_name: Name for the session file.
            sessions_dir: Directory to store session files.
            alerts_log_path: Path to JSON log file for alerts.
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.channel_entity = channel_entity
        self.session_name = session_name
        self.sessions_dir = Path(sessions_dir)
        self.alerts_log_path = Path(alerts_log_path)
        self.parser = AlertParser()
        self.db = get_database()

        # Ensure sessions directory exists
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self) -> Path:
        """Get path to session file."""
        return self.sessions_dir / f"{self.session_name}.session"

    def _create_client(self) -> TelegramClient:
        """Create and return TelegramClient."""
        return TelegramClient(
            str(self._get_session_path()),
            self.api_id,
            self.api_hash,
        )

    def _log_alert_json(self, alert: AlertMessage) -> None:
        """Append alert as a JSON line to alerts.log."""
        with open(self.alerts_log_path, "a") as f:
            f.write(json.dumps(alert.to_dict(), ensure_ascii=False) + "\n")

    async def handle_message(self, event) -> None:
        """Handle incoming message from the channel.

        Args:
            event: Telethon Message event.
        """
        message_text = event.message.message or ""
        if not message_text.strip():
            return

        # Parse the message
        alert = self.parser.parse(message_text)
        if alert is None:
            logger.debug(f"Skipping non-alert message: {message_text[:50]}")
            return

        # Log to JSON file
        self._log_alert_json(alert)
        logger.info(f"[RECEIVED] {alert.symbol} @ {alert.price}")

        # Store in database
        row_id = self.db.insert_alert(alert)
        logger.debug(f"Stored alert with row_id={row_id}")

    async def start_listening(self) -> None:
        """Connect to Telegram and start listening to the channel."""
        client = self._create_client()

        await client.start(phone=self.phone)

        logger.info(f"Connected to Telegram as {self.phone}")

        # Get the channel entity
        try:
            channel = await client.get_entity(self.channel_entity)
            logger.info(f"Listening on channel: {self.channel_entity}")
        except Exception as e:
            logger.error(f"Could not find channel '{self.channel_entity}': {e}")
            raise

        # Listen for new messages
        client.add_event_handler(self.handle_message)

        # Keep running
        logger.info("Listener started. Press Ctrl+C to stop.")
        await client.run_until_disconnected()


def run_listener(config_path: str = "config/config.yaml") -> None:
    """Run the listener from config file."""
    import yaml

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    telegram_cfg = config["telegram"]
    channel_cfg = config["channel"]
    app_cfg = config.get("app", {})

    listener = TradingViewListener(
        api_id=telegram_cfg["api_id"],
        api_hash=telegram_cfg["api_hash"],
        phone=telegram_cfg["phone"],
        channel_entity=channel_cfg["entity"],
        session_name=telegram_cfg.get("session_name", "listener_session"),
        sessions_dir=config.get("sessions_dir", "sessions"),
        alerts_log_path=app_cfg.get("alerts_log", "alerts.log"),
    )

    # Configure logging
    log_level = app_cfg.get("log_level", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import asyncio
    asyncio.run(listener.start_listening())


if __name__ == "__main__":
    run_listener()