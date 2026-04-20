#!/usr/bin/env python3
"""Entry point for TradingView Signal Generator listener.

Usage:
    python run_listener.py              # Start listener (requires session already set up)
    python run_listener.py --setup      # Interactive first-run setup for Telegram auth
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml


def interactive_setup() -> None:
    """Walk the user through first-run session setup."""
    print("=== TradingView Signal Generator — Interactive Setup ===\n")

    config_path = Path("config/config.yaml")
    if not config_path.exists():
        print("ERROR: config/config.yaml not found. Run from project root.")
        sys.exit(1)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Prompt for API credentials
    print("Enter your Telegram API credentials from https://my.telegram.org:")
    api_id = input("  API ID: ").strip()
    api_hash = input("  API Hash: ").strip()
    phone = input("  Phone number (with country code, e.g. +12125551234): ").strip()

    if not api_id or not api_hash or not phone:
        print("ERROR: All fields are required.")
        sys.exit(1)

    # Update config
    config["telegram"]["api_id"] = api_id
    config["telegram"]["api_hash"] = api_hash
    config["telegram"]["phone"] = phone

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print("\nConfig updated. Starting interactive Telegram login...")

    # Run Telethon setup flow
    from telethon import TelegramClient

    sessions_dir = Path(config.get("sessions_dir", "sessions"))
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_name = config["telegram"].get("session_name", "listener_session")

    client = TelegramClient(str(sessions_dir / f"{session_name}.session"), api_id, api_hash)

    print("\nA verification code will be sent to your Telegram app.")
    print("Enter it when prompted.\n")

    client.start(phone=phone)

    print("\nSession created successfully!")
    print(f"Session stored in: {sessions_dir / f'{session_name}.session'}")
    print("\nYou can now run: python run_listener.py")


def main() -> None:
    """Run the listener."""
    parser = argparse.ArgumentParser(description="TradingView Signal Generator Listener")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive first-run setup for Telegram authentication",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file (default: config/config.yaml)",
    )

    args = parser.parse_args()

    if args.setup:
        interactive_setup()
        return

    # Normal run
    from src.listener import run_listener

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_listener(config_path=args.config)


if __name__ == "__main__":
    main()