"""Alert message parser for TradingView webhook format.

TradingView + LuxAlgo alert formats:
    Standard:   "TradingView Alert for SPX, Price = 7095.15"
    RSI/MACD/BB:"LuxAlgo RSI: 65.2 | MACD: 0.45 | Signal: 0.38 | Hist: 0.07 | BB: 7030/7050/7070"
    Exit:       "LuxAlgo Exit Long @ 7095.15 | Entry: 7070.00 | P&L: +25.15 (+0.36%)"
    Confirmation+:"LuxAlgo Confirmation+ Long | Price: 7095.15 | RSI: 65 | MACD: 0.45"
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Literal


# ────────────────────────────────────────────────
#              Dataclasses
# ────────────────────────────────────────────────

@dataclass
class AlertMessage:
    """Parsed TradingView/LuxAlgo alert message."""

    raw_text: str
    symbol: Optional[str] = None
    price: Optional[float] = None
    received_at: Optional[str] = None
    parsed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # LuxAlgo-specific fields
    alert_type: Optional[str] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    # Exit fields
    direction: Optional[Literal["Long", "Short"]] = None
    entry_price: Optional[float] = None
    pnl_points: Optional[float] = None
    pnl_pct: Optional[float] = None
    exit_reason: Optional[str] = None
    # Confirmation+ specific
    signal: Optional[Literal["Long", "Short", "Neutral"]] = None

    def to_dict(self) -> dict:
        """Serialize to alerts.log JSON format."""
        result: dict = {
            "ts": self.received_at,
            "symbol": self.symbol,
            "price": self.price,
            "raw": self.raw_text,
        }
        if self.alert_type:
            result["alert_type"] = self.alert_type
        if self.rsi is not None:
            result["rsi"] = self.rsi
        if self.macd is not None:
            result["macd"] = self.macd
        if self.macd_signal is not None:
            result["macd_signal"] = self.macd_signal
        if self.macd_hist is not None:
            result["macd_hist"] = self.macd_hist
        if self.bb_upper is not None:
            result["bb_upper"] = self.bb_upper
        if self.bb_middle is not None:
            result["bb_middle"] = self.bb_middle
        if self.bb_lower is not None:
            result["bb_lower"] = self.bb_lower
        if self.direction is not None:
            result["direction"] = self.direction
        if self.entry_price is not None:
            result["entry_price"] = self.entry_price
        if self.pnl_points is not None:
            result["pnl_points"] = self.pnl_points
        if self.pnl_pct is not None:
            result["pnl_pct"] = self.pnl_pct
        if self.exit_reason is not None:
            result["exit_reason"] = self.exit_reason
        if self.signal is not None:
            result["signal"] = self.signal
        return result


# ────────────────────────────────────────────────
#              Parser
# ────────────────────────────────────────────────

class AlertParser:
    """Parser for TradingView and LuxAlgo alert messages.

    Supported formats:
        1. Standard TradingView:
           "TradingView Alert for SPX, Price = 7095.15"

        2. LuxAlgo RSI/MACD/BB:
           "LuxAlgo RSI: 65.2 | MACD: 0.45 | Signal: 0.38 | Hist: 0.07 |
            BB Upper: 7030.00 | BB Middle: 7050.00 | BB Lower: 7070.00"

        3. LuxAlgo Exit:
           "LuxAlgo Exit Long @ 7095.15 | Entry: 7070.00 |
            P&L: +25.15 (+0.36%) | Reason: Trailing Stop"

        4. LuxAlgo Confirmation+:
           "LuxAlgo Confirmation+ Long | Price: 7095.15 |
            RSI: 65 | MACD: 0.45 | Signal: 0.38"
    """

    # ── Format 1: Standard TradingView ──────────────────────────
    PATTERN_TRADINGVIEW = re.compile(
        r"""
        ^\s*TradingView\s+Alert\s+for\s+
        (?P<symbol>[A-Za-z0-9_]+)\s*,\s*
        Price\s*=\s*
        (?P<price>[\d.]+)
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    # ── Format 2: LuxAlgo RSI/MACD/BB ──────────────────────────
    PATTERN_LUXALGO_RSI_MACD_BB = re.compile(
        r"""
        ^\s*LuxAlgo\s+RSI\s*:\s*(?P<rsi>[\d.]+)\s*\|?\s*
        MACD\s*:\s*(?P<macd>[-\d.]+)\s*\|?\s*
        Signal\s*:\s*(?P<macd_signal>[-\d.]+)\s*\|?\s*
        Hist\s*:\s*(?P<macd_hist>[-\d.]+)\s*\|?\s*
        BB\s*(?:Upper\s*:?\s*|Upper:\s*)(?P<bb_upper>[\d.]+)\s*\|?\s*
        (?:BB\s*)?Middle\s*:\s*(?P<bb_middle>[\d.]+)\s*\|?\s*
        (?:BB\s*)?Lower\s*:\s*(?P<bb_lower>[\d.]+)
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    # ── Format 3: LuxAlgo Exit ─────────────────────────────────
    # P&L sign is on the points value; pct has its own sign inside parentheses
    PATTERN_LUXALGO_EXIT = re.compile(
        r"""
        ^\s*LuxAlgo\s+Exit\s+(?P<direction>Long|Short)\s*@\s*
        (?P<price>[\d.]+)\s*\|?\s*
        Entry\s*:\s*(?P<entry_price>[\d.]+)\s*\|?\s*
        P&L\s*:\s*(?P<pnl_sign>[+\-])?(?P<pnl_points>[\d.]+)\s*
        \(\s*(?P<pnl_pct>[+\-]?[\d.]+)%\s*\)\s*\|?\s*
        Reason\s*:\s*(?P<exit_reason>.+)
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    # ── Format 4: LuxAlgo Confirmation+ ───────────────────────
    # Symbol may appear as a bare word anywhere: "Confirmation+ Long | SPX | Price: ..."
    PATTERN_LUXALGO_CONF = re.compile(
        r"""
        ^\s*LuxAlgo\s+Confirmation\+\s+
        (?P<signal>Long|Short|Neutral)\s*\|?\s*
        (?:(?P<symbol_word>[A-Z]{2,6})\s*\|?\s*)?
        Price\s*:\s*(?P<price>[\d.]+)\s*\|?\s*
        RSI\s*:\s*(?P<rsi>[\d.]+)\s*\|?\s*
        MACD\s*:\s*(?P<macd>[-\d.]+)\s*\|?\s*
        Signal\s*:\s*(?P<macd_signal>[-\d.]+)
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    KNOWN_TICKERS = {"SPX", "SPY", "QQQ", "IWM", "DIA", "NDX", "RUT", "TSLA", "AAPL", "NVDA"}

    _SYMBOL_STOPWORDS = {
        "LUXALGO", "RSI", "MACD", "SIGNAL", "HIST", "HISTOGRAM",
        "BB", "UPPER", "MIDDLE", "LOWER", "PRICE", "ENTRY", "REASON",
        "TRAILING", "STOP", "LONG", "SHORT", "CONFIRMATION", "NEUTRAL",
        "EXIT", "TARGET", "HIT", "LOSS", "ALERT", "TRADINGVIEW",
    }

    _SYMBOL_PATTERN = re.compile(r"\b([A-Z]{2,6})\b")
    _PRICE_NUM_PATTERN = re.compile(r"\b([1-9]\d{3,4})\.\d{2}\b")

    def parse(self, text: str) -> Optional[AlertMessage]:
        """Parse raw text into AlertMessage."""
        if not text or not text.strip():
            return None

        original = text.strip()

        # 1. Standard TradingView
        mv = self.PATTERN_TRADINGVIEW.search(original)
        if mv:
            symbol = mv.group("symbol").upper()
            try:
                price = float(mv.group("price"))
            except (ValueError, TypeError):
                return None
            now_utc = datetime.now(timezone.utc).isoformat()
            return AlertMessage(
                raw_text=original,
                symbol=symbol,
                price=price,
                received_at=now_utc,
                alert_type="tradingview",
            )

        # 2. LuxAlgo RSI/MACD/BB
        rv = self.PATTERN_LUXALGO_RSI_MACD_BB.search(original)
        if rv:
            return self._build_rsi_macd_bb(original, rv)

        # 3. LuxAlgo Exit
        ev = self.PATTERN_LUXALGO_EXIT.search(original)
        if ev:
            return self._build_exit(original, ev)

        # 4. LuxAlgo Confirmation+
        cv = self.PATTERN_LUXALGO_CONF.search(original)
        if cv:
            return self._build_confirmation_plus(original, cv)

        return None

    def _build_rsi_macd_bb(self, original: str, match: re.Match) -> AlertMessage:
        symbol = self._extract_symbol(original)
        now_utc = datetime.now(timezone.utc).isoformat()
        return AlertMessage(
            raw_text=original,
            symbol=symbol,
            price=None,
            received_at=now_utc,
            alert_type="rsi_macd_bb",
            rsi=float(match.group("rsi")),
            macd=float(match.group("macd")),
            macd_signal=float(match.group("macd_signal")),
            macd_hist=float(match.group("macd_hist")),
            bb_upper=float(match.group("bb_upper")),
            bb_middle=float(match.group("bb_middle")),
            bb_lower=float(match.group("bb_lower")),
        )

    def _build_exit(self, original: str, match: re.Match) -> AlertMessage:
        """Build AlertMessage from LuxAlgo Exit regex match."""
        # pnl_points has sign prefix; pnl_pct already has its own sign inside ()
        pnl_sign_str = match.group("pnl_sign") or "+"
        pnl_sign = -1.0 if pnl_sign_str == "-" else 1.0
        pnl_points = pnl_sign * float(match.group("pnl_points"))
        # pnl_pct captured as-is (includes own sign): do NOT re-apply pnl_sign
        pnl_pct = float(match.group("pnl_pct"))

        symbol = self._extract_symbol(original)
        now_utc = datetime.now(timezone.utc).isoformat()
        return AlertMessage(
            raw_text=original,
            symbol=symbol,
            price=float(match.group("price")),
            received_at=now_utc,
            alert_type="exit",
            direction=match.group("direction"),
            entry_price=float(match.group("entry_price")),
            pnl_points=pnl_points,
            pnl_pct=pnl_pct,
            exit_reason=match.group("exit_reason").strip(),
        )

    def _build_confirmation_plus(
        self, original: str, match: re.Match
    ) -> AlertMessage:
        symbol = self._extract_symbol(original)
        # Override with explicit symbol_word if captured
        if match.group("symbol_word"):
            symbol = match.group("symbol_word")
        now_utc = datetime.now(timezone.utc).isoformat()
        return AlertMessage(
            raw_text=original,
            symbol=symbol,
            price=float(match.group("price")),
            received_at=now_utc,
            alert_type="confirmation_plus",
            signal=match.group("signal"),
            rsi=float(match.group("rsi")),
            macd=float(match.group("macd")),
            macd_signal=float(match.group("macd_signal")),
        )

    def _extract_symbol(self, text: str) -> Optional[str]:
        """Extract a likely ticker symbol from raw text.

        1. Known tickers (SPX, QQQ, etc.)
        2. Look for 4-digit price numbers — these are NOT tickers, so return None
           (distinguishes equity prices from RSI 0-100)
        3. Any other all-caps word not in stopwords
        """
        # 1. Known tickers
        for m in self._SYMBOL_PATTERN.finditer(text):
            word = m.group(1)
            if word in self.KNOWN_TICKERS:
                return word

        # 2. 4-digit price present — not a ticker, symbol unavailable
        if self._PRICE_NUM_PATTERN.search(text):
            return None

        # 3. Generic fallback
        for m in self._SYMBOL_PATTERN.finditer(text):
            word = m.group(1)
            if word not in self._SYMBOL_STOPWORDS and len(word) >= 2:
                return word

        return None

    def parse_or_raise(self, text: str) -> AlertMessage:
        """Parse or raise ValueError if invalid."""
        result = self.parse(text)
        if result is None:
            raise ValueError(f"Could not parse TradingView alert: {text!r}")
        return result
