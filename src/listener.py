"""Telethon listener for TradingView alerts from private Telegram channel."""

import json
import logging
import sys
from pathlib import Path

from telethon import TelegramClient

from .parser import AlertParser, AlertMessage

logger = logging.getLogger(__name__)


class Listener:
    """Listens to a private Telegram channel for TradingView alert messages."""

    def __init__(
        self,
        api_id: str,
        api_hash: str,
        phone: str,
        channel_name: str,
        session_name: str = "listener_session",
        sessions_dir: str = "sessions",
        log_file: str = "alerts.log",
    ):
        """Initialize the listener.

        Args:
            api_id: Telegram API ID.
            api_hash: Telegram API Hash.
            phone: Telegram phone number.
            channel_name: Channel name to listen on.
            session_name: Name for the session file.
            sessions_dir: Directory to store session files.
            log_file: Path to JSON log file for alerts.
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.channel_name = channel_name
        self.session_name = session_name
        self.sessions_dir = Path(sessions_dir)
        self.log_file = Path(log_file)
        self.parser = AlertParser()

        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self) -> Path:
        """Get path to session file."""
        return self.sessions_dir / f"{self.session_name}.session"

    def _log_alert_json(self, alert: AlertMessage) -> None:
        """Append alert as a JSON line to alerts.log."""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(alert.to_dict(), ensure_ascii=False) + "\n")

    async def handle_message(self, event) -> None:
        """Handle incoming message from the channel.

        Args:
            event: Telethon Message event.
        """
        message_text = event.message.message or ""
        if not message_text.strip():
            return

        alert = self.parser.parse(message_text)
        if alert is None:
            logger.debug(f"Skipping non-alert message: {message_text[:50]}")
            return

        self._log_alert_json(alert)
        logger.info(f"[RECEIVED] {alert.symbol} @ {alert.price}")

    async def run(self) -> None:
        """Connect to Telegram and start listening to the channel."""
        client = TelegramClient(
            str(self._get_session_path()),
            self.api_id,
            self.api_hash,
        )

        await client.start(phone=self.phone)
        logger.info(f"Connected to Telegram as {self.phone}")

        try:
            channel = await client.get_entity(self.channel_name)
            logger.info(f"Listening on channel: {self.channel_name}")
        except Exception as e:
            logger.error(f"Could not find channel '{self.channel_name}': {e}")
            raise

        client.add_event_handler(self.handle_message)
        logger.info("Listener started. Press Ctrl+C to stop.")
        await client.run_until_disconnected()


def run_listener(config_path: str = "config/config.yaml") -> None:
    """Run the listener from config file."""
    import yaml

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    listener_cfg = config.get("listener", {})
    telegram_cfg = config.get("telegram", {})

    listener = Listener(
        api_id=str(telegram_cfg.get("api_id", "")),
        api_hash=telegram_cfg.get("api_hash", ""),
        phone=telegram_cfg.get("phone", ""),
        channel_name=listener_cfg.get("channel_name", "TradingView Alerts"),
        session_name=telegram_cfg.get("session_name", "listener_session"),
        sessions_dir="sessions",
        log_file=listener_cfg.get("log_file", "alerts.log"),
    )

    import asyncio
    asyncio.run(listener.run())
