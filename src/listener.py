"""Telethon listener for TradingView alerts from private Telegram channel."""

import json
import logging
from pathlib import Path

from telethon import TelegramClient
from telethon.events import NewMessage

from .parser import AlertParser, AlertMessage

logger = logging.getLogger(__name__)


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
        log_file: str = "alerts.log",
    ):
        """Initialize the listener.

        Args:
            api_id: Telegram API ID.
            api_hash: Telegram API Hash.
            phone: Telegram phone number.
            channel_entity: Channel name, username, or numeric chat_id (e.g. "-1003946119741").
            session_name: Name for the session file.
            sessions_dir: Directory to store session files.
            log_file: Path to JSON log file for alerts.
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.channel_entity = channel_entity
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

    async def _resolve_channel(self, client: TelegramClient):
        """Resolve channel entity from name, username, or numeric chat_id.

        For numeric IDs, iterates through dialogs to find a matching channel.
        """
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
            f"Could not find channel with id '{self.channel_entity}' in your dialogs. "
            f"Make sure the bot/user has joined the channel."
        )

    async def handle_message(self, event: NewMessage) -> None:
        """Handle incoming message from the channel.

        Args:
            event: Telethon NewMessage event.
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

        channel = await self._resolve_channel(client)
        channel_title = getattr(channel, 'title', self.channel_entity)
        logger.info(f"Listening on channel: {channel_title}")

        # Filter: only NewMessage events from this specific channel
        client.add_event_handler(
            self.handle_message,
            NewMessage(chats=[channel])
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
    listener_cfg = config.get("listener", {})

    channel_entity = channel_cfg.get(
        "entity",
        listener_cfg.get("channel_name", "TradingView Alerts")
    )

    listener = Listener(
        api_id=str(telegram_cfg.get("api_id", "")),
        api_hash=telegram_cfg.get("api_hash", ""),
        phone=telegram_cfg.get("phone", ""),
        channel_entity=channel_entity,
        session_name=telegram_cfg.get("session_name", "listener_session"),
        sessions_dir=telegram_cfg.get("sessions_dir", "sessions"),
        log_file=listener_cfg.get("alerts_log", "alerts.log"),
    )

    import asyncio
    asyncio.run(listener.run())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s,%(levelname)s %(name)s: %(message)s",
    )
    run_listener()