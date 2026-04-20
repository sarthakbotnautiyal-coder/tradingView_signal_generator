# TradingView Signal Generator

## Overview

A Telethon-based listener that receives TradingView webhook alerts from a private Telegram channel, logs them, and (in Phase 2) evaluates OTM bid premiums against historical data to decide whether to notify the user.

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
│   ├── otm_lookup.py         # Fetch current OTM from api.0dtespx.com (or SPX fetcher)
│   ├── comparator.py         # Compare current OTM vs historical summary
│   ├── notifier.py           # Send Telegram notification to user
│   └── db/
│       ├── __init__.py
│       └── database.py       # SQLite schema for alert_log
├── tests/
│   ├── test_parser.py
│   └── test_comparator.py
├── sessions/
│   └── session.session       # Telethon session file (gitignored)
├── run_listener.py           # Entry point — starts the listener
├── run_comparator.py         # Standalone: run comparison on demand (for testing)
└── DesignDocs/
    └── signal-generator.md
```

---

## Phase 1 — Listener (This Build)

### Goal
Receive TradingView alert messages from the private channel and log them. No decisions, no notifications — just capture and store.

### Telethon Setup

**config/config.yaml:**
```yaml
telegram:
  api_id: "YOUR_API_ID"          # Placeholder — replace with real value
  api_hash: "YOUR_API_HASH"      # Placeholder — replace with real value
  session_name: "listener_session"
  phone: "+1234567890"           # Your Telegram number

channel:
  entity: "TradingView Alerts"   # Channel name or username
  # Alternatively use channel hash if name is ambiguous

app:
  log_level: "INFO"
```

**Session file:** `sessions/listener_session.session` — created on first login, reused thereafter.

### Message Parsing

TradingView alert format:
```
TradingView Alert for SPX, Price = 7095.15
```

Parser extracts:
- `symbol` = "SPX" (from "Alert for SPX")
- `price` = 7095.15 (from "Price = X")

Design for extensible parsing — add more fields as TradingView alerts evolve.

```python
class AlertMessage:
    raw_text: str
    symbol: str
    price: float
    timestamp: datetime
    parsed_at: datetime
```

### Alert Log Table

```sql
CREATE TABLE alert_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_message     TEXT NOT NULL,
    symbol          TEXT,
    price           REAL,
    received_at     TEXT NOT NULL,    -- UTC ISO8601
    processed       INTEGER DEFAULT 0, -- 0 = raw, 1 = processed (Phase 2+)
    phase           INTEGER DEFAULT 1  -- 1 = listener only, 2 = comparison done
);
```

### Listener Flow

1. Connect to Telegram using session file (or interactive login if first run)
2. Join/listen to the private channel
3. On each new message:
   - Parse with `AlertParser`
   - Store in `alert_log`
   - Log: `[RECEIVED] SPX @ 7095.15`
4. Keep running (polling / event-driven via Telethon)

### First Run Setup

```bash
python run_listener.py --setup
```
- Prompts for phone number, sends OTP via Telegram
- Creates session file in `sessions/`
- Stores session, reuses on subsequent runs

---

## Phase 2 — OTM Comparison + Notification

### Trigger
After listener logs an alert, a separate process (or same listener with extra step) does:

1. **Fetch current OTM data** — call `api.0dtespx.com/aggregateData` with today's date
2. **Determine VIX bucket** — classify current VIX into `<15 | 15-20 | 20-25 | 25-30 | >30`
3. **Determine time bucket** — current HH:MM → 5-min bucket (09:30 → 15:55)
4. **Look up historical avg** — query `market_data_summary` for `(bucket_start, vix_bucket)` → `avg_spx_otm_bids`
5. **Compare** — if current OTM > historical avg × `threshold_multiplier` → send alert
6. **Log result** — update `alert_log` with comparison result

### Threshold Config (config/config.yaml)

```yaml
comparison:
  threshold_multiplier: 1.2   # Alert if current OTM > 120% of historical avg
  min_vix_to_evaluate: 15    # Skip if VIX < 15 (low premium environment)
  notification_channel: "me"  # Telegram username or chat ID to send alerts
```

### Comparator Flow

```python
def evaluate_alert(alert: AlertMessage) -> Optional[ComparisonResult]:
    # 1. Fetch current market data
    market_data = fetch_current_otm()  # from api.0dtespx.com

    # 2. Classify
    vix_bucket = classify_vix(market_data.vix)
    bucket_start = compute_time_bucket(market_data.timestamp)

    # 3. Historical lookup
    historical = db.get_historical_avg(bucket_start, vix_bucket)

    # 4. Compare
    ratio = market_data.spx_otm_bids / historical.avg_spx_otm_bids

    return ComparisonResult(
        current_otm=market_data.spx_otm_bids,
        historical_avg=historical.avg_spx_otm_bids,
        ratio=ratio,
        should_alert=ratio >= threshold_multiplier,
        vix_bucket=vix_bucket,
        bucket_start=bucket_start
    )
```

---

## Phase 3+ (Deferred)

- Multi-symbol support (SPX, QQQ, etc.)
- Strategy routing (different rules per symbol)
- Trade execution (hook into broker API)
- Dashboard / web UI

---

## Key Design Decisions

### SQLite for alert_log
Lightweight, no separate DB server needed. Can migrate to Postgres later if needed.

### SPX Historical Fetcher for OTM lookup
Phase 2 uses the same `api.0dtespx.com` that SPX Historical Fetcher uses. Options:
- **Option A:** Import from `spx_historical_fetcher` as a library (tight coupling)
- **Option B:** Re-implement the lightweight fetch here (duplicate code but cleaner separation)
- **Option C:** Use `spx_historical_fetcher` as a submodule

Recommendation: Option B — keep it simple, the fetch is just one function.

### Historical Summary Data
The summary table (`market_data_summary`) lives in the SPX Historical Fetchers SQLite DB. For Phase 2, this repo needs read-only access to that DB. Path configurable via `config.yaml`:

```yaml
historical_db_path: "/Users/ubexbot/.openclaw/workspace-venkat/spx_historical_fetcher/market_data.db"
```

### VIX Bucket Logic (Phase 2)
Same as SPX Historical Fetcher:
- `vix < 15` → `<15`
- `15 ≤ vix < 20` → `15-20`
- `20 ≤ vix < 25` → `20-25`
- `25 ≤ vix < 30` → `25-30`
- `vix ≥ 30` → `>30`

### 5-min Bucket Logic (Phase 2)
Same as SPX Historical Fetcher:
- `09:30 ≤ time < 09:35` → `09:30`
- `09:35 ≤ time < 09:40` → `09:35`
- ...
- `15:55 ≤ time < 16:00` → `15:55`

---

## Setup Instructions

```bash
# Clone
git clone https://github.com/sarthakbotnautiyal-coder/tradingView_signal_generator.git
cd tradingView_signal_generator

# Install deps
pip3 install --break-system-packages -r requirements.txt

# First run — interactive session setup
python run_listener.py --setup

# Update config/config.yaml with real API credentials

# Start listener
python run_listener.py
```

---

## Out of Scope (Phase 1)
- No comparison logic (Phase 2)
- No user notifications (Phase 2)
- No multi-symbol support
- No trade execution
- No web UI/dashboard

---

## Dependencies (requirements.txt)

```
telethon>=1.35.0
pyyaml>=6.0
requests>=2.31.0
```

---

## Test Plan (Phase 1)

| Test | Description |
|------|-------------|
| `test_parser.py` | Parses sample TradingView messages, extracts symbol + price |
| `test_parser_edge_cases` | Empty message, missing fields, unusual formats |
| `test_listener_db` | Write alert to DB, read back, verify fields |
| `test_time_bucket` | Verify 5-min bucket computation |
| `test_vix_bucket` | Verify VIX classification |

---

## TODO

### Phase 1
- [ ] Create repo
- [ ] config/config.yaml with placeholder API creds
- [ ] Telethon client with session management
- [ ] Alert message parser
- [ ] alert_log SQLite table
- [ ] run_listener.py entry point
- [ ] First-run setup script
- [ ] Tests
- [ ] SPEC.md