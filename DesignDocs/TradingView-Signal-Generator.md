# TradingView Signal Generator — Design Doc

## Overview

A Telethon-based listener that receives TradingView webhook alerts from a private Telegram channel and logs them. Phase 2 evaluates OTM bid premiums against historical data to decide whether to notify the user.

**Repo:** `sarthakbotnautiyal-coder/tradingView_signal_generator`
**Stack:** Python 3, Telethon, SQLite, SPX Historical Fetcher (`api.0dtespx.com`)

---

## Architecture

```
TradingView → Private Telegram Channel → Telethon Listener → Log
                                                      ↓
                                            Phase 2: OTM Comparison
                                                      ↓
                                            Historical Summary DB
                                                      ↓
                                            Telegram User Alert (if premium met)
```

---

## Project Structure

```
tradingView_signal_generator/
├── SPEC.md
├── requirements.txt
├── config/
│   └── config.yaml          # Telegram API creds, thresholds, paths
├── src/
│   ├── __init__.py
│   ├── listener.py           # Telethon client + channel listener
│   ├── parser.py             # Parse TradingView alert messages
│   └── db/
│       ├── __init__.py
│       └── database.py       # SQLite schema for alert_log
├── tests/
│   └── test_parser.py
├── sessions/                  # Telethon session files (gitignored)
├── run_listener.py           # Entry point — starts the listener
└── DesignDocs/
    └── TradingView-Signal-Generator.md
```

---

## Phase 1 — Listener

### Goal
Receive TradingView alert messages from the private channel and log them. No decisions, no notifications — just capture and store.

### TradingView Message Format

```
TradingView Alert for SPX, Price = 7095.15
```

### AlertMessage Dataclass

```python
@dataclass
class AlertMessage:
    raw_text: str       # Full raw message
    symbol: str         # e.g. "SPX"
    price: float        # e.g. 7095.15
    received_at: str    # UTC ISO8601 (when received)
    parsed_at: str      # UTC ISO8601 (when parsed)
```

### alerts.log — JSON Lines Format

One JSON object per line:
```json
{"ts": "2026-04-20T14:30:00Z", "symbol": "SPX", "price": 7095.15, "raw": "TradingView Alert for SPX, Price = 7095.15"}
```

- `ts` = UTC timestamp when received
- `symbol` = parsed symbol or null if unparseable
- `price` = parsed price or null if unparseable
- `raw` = full raw message

If parsing fails, log the raw message with null symbol/price — don't crash the listener.

---

## Phase 2 — OTM Comparison + Notification

### Trigger
After listener logs an alert, a separate process evaluates:

1. **Fetch current OTM** — call `api.0dtespx.com/aggregateData`
2. **VIX bucket** — `<15 | 15-20 | 20-25 | 25-30 | >30`
3. **Time bucket** — 5-min bucket (09:30 → 15:55)
4. **Compare** — if current OTM > historical avg × threshold_multiplier → send alert

---

## Key Design Decisions

- SQLite `alert_log` table for persistent storage
- Telethon session file stored in `sessions/` (gitignored)
- Graceful degradation: if parsing fails, log raw message with null fields
- Config-driven: all paths, credentials, thresholds in `config/config.yaml`
